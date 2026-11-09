"""Sprint 1 acceptance tests: data integrity, snapshots, refresh, freshness and migrations."""
import sqlite3
import threading
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, snapshots
from app import main as main_module
from app.dataset import SERVICES, build_dataset, content_hash, validate_dataset


def _refresh(client, **body):
    return client.post("/api/dataset/refresh", json=body or None)


def _active(client):
    return client.get("/api/dataset").json()["snapshot_id"]


def _count(table):
    with closing(sqlite3.connect(db.db_path())) as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ------------------------------------------------------------- cost calculations ---

def test_dashboard_total_equals_sum_of_service_costs(client):
    d = client.get("/api/dashboard").json()
    assert d["total_spend"] == round(sum(d["service_breakdown"].values()), 2)


def test_every_month_total_equals_its_billing_records(client):
    d = client.get("/api/dashboard").json()
    spend = client.get("/api/spend").json()
    for point in d["monthly_trend"]:
        assert point["total"] == round(sum(r["cost"] for r in spend if r["month"] == point["month"]), 2)
    assert d["monthly_trend"][-1]["total"] == d["total_spend"]


def test_service_breakdown_covers_every_service_once(client):
    d = client.get("/api/dashboard").json()
    assert sorted(d["service_breakdown"]) == sorted(SERVICES)


# ---------------------------------------------------- one dataset, one snapshot ---

def test_all_endpoints_report_the_same_snapshot_and_dataset(client):
    responses = {
        "dashboard": client.get("/api/dashboard"),
        "recommendations": client.get("/api/recommendations"),
        "anomalies": client.get("/api/anomalies"),
        "history": client.get("/api/anomalies/history"),
        "resources": client.get("/api/resources"),
        "health": client.get("/api/health"),
        "dataset": client.get("/api/dataset"),
        "copilot": client.post("/api/copilot", json={"question": "What should I investigate first?"}),
    }
    snap_ids = {r.headers["X-Snapshot-Id"] for r in responses.values()}
    data_ids = {r.headers["X-Dataset-Id"] for r in responses.values()}
    assert len(snap_ids) == 1 and len(data_ids) == 1
    sid, did = snap_ids.pop(), data_ids.pop()
    assert responses["dashboard"].json()["snapshot_id"] == sid
    assert responses["dataset"].json()["dataset_id"] == did
    assert {r["snapshot_id"] for r in responses["recommendations"].json()} == {sid}
    assert {r["dataset_id"] for r in responses["recommendations"].json()} == {did}
    assert {a["snapshot_id"] for a in responses["history"].json()["anomalies"]} == {sid}
    assert {a["dataset_id"] for a in responses["anomalies"].json()} == {did}
    assert responses["copilot"].json()["snapshot_id"] == sid


def test_snapshot_id_and_dataset_id_are_distinct_identifiers(client):
    meta = client.get("/api/dataset").json()
    assert meta["snapshot_id"].startswith("snap-") and meta["dataset_id"].startswith("ds-")
    first = meta["snapshot_id"]
    _refresh(client, seed=99)
    back = _refresh(client, seed=17).json()  # same content as the first snapshot again
    assert back["status"] == "created"
    assert back["snapshot"]["dataset_id"] == meta["dataset_id"]
    assert back["snapshot"]["snapshot_id"] != first


def test_persisted_snapshot_round_trips_exactly(client):
    ds = snapshots.load_dataset()
    built = build_dataset(date.fromisoformat(ds["reference_date"]), ds["seed"])
    assert ds["spend"] == built["spend"]
    assert ds["resources"] == built["resources"]
    assert ds["dataset_id"] == built["dataset_id"] == content_hash(ds["seed"], ds["spend"], ds["resources"])


def test_snapshot_survives_restart_without_regenerating(client):
    before = client.get("/api/dataset").json()
    snapshots.clear_cache()
    from app.main import app
    with TestClient(app) as again:  # startup runs again against the same database
        after = again.get("/api/dataset").json()
    assert after["snapshot_id"] == before["snapshot_id"]
    assert after["created_at"] == before["created_at"]
    assert _count("dataset_snapshots") == 1


def test_stored_data_tampering_is_detected(client):
    sid = _active(client)
    with closing(sqlite3.connect(db.db_path())) as c:
        c.execute("UPDATE billing_records SET cost = cost + 1 WHERE snapshot_id = ? AND rowid = "
                  "(SELECT MIN(rowid) FROM billing_records WHERE snapshot_id = ?)", (sid, sid))
        c.commit()
    snapshots.clear_cache()
    with pytest.raises(RuntimeError, match="integrity"):
        snapshots.load_dataset(sid)


def test_database_allows_only_one_active_snapshot(client):
    _refresh(client, seed=99)
    with closing(sqlite3.connect(db.db_path())) as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE dataset_snapshots SET status = 'active'")


# -------------------------------------------------------------------- refresh ---

def test_identical_refresh_keeps_snapshot_and_records_run(client):
    before = _active(client)
    body = _refresh(client).json()
    assert body["status"] == "unchanged"
    assert body["snapshot"]["snapshot_id"] == before == _active(client)
    assert _count("dataset_snapshots") == 1
    runs = client.get("/api/dataset/refresh-history").json()
    assert [r["status"] for r in runs[:2]] == ["unchanged", "created"]  # newest first; bootstrap created
    assert runs[1]["trigger"] == "bootstrap"


def test_refresh_creates_and_activates_new_snapshot(client):
    old = client.get("/api/dataset").json()
    body = _refresh(client, seed=99).json()
    assert body["status"] == "created"
    new_id = body["snapshot"]["snapshot_id"]
    assert new_id != old["snapshot_id"] and _active(client) == new_id
    assert body["run"]["previous_snapshot_id"] == old["snapshot_id"]
    listing = client.get("/api/dataset/snapshots").json()
    status = {s["snapshot_id"]: s["status"] for s in listing["snapshots"]}
    assert listing["active_snapshot_id"] == new_id
    assert status == {new_id: "active", old["snapshot_id"]: "superseded"}
    assert client.get("/api/dashboard").json()["snapshot_id"] == new_id


def test_historical_snapshot_remains_accessible(client):
    old = client.get("/api/dashboard").json()
    old_recs = client.get("/api/recommendations").json()
    _refresh(client, seed=99)
    assert client.get("/api/dashboard").json()["total_spend"] != old["total_spend"]
    q = f"?snapshot_id={old['snapshot_id']}"
    again = client.get("/api/dashboard" + q).json()
    assert again["total_spend"] == old["total_spend"] and again["snapshot_id"] == old["snapshot_id"]
    assert [r["id"] for r in client.get("/api/recommendations" + q).json()] == [r["id"] for r in old_recs]
    meta = client.get(f"/api/dataset/snapshots/{old['snapshot_id']}").json()
    assert meta["snapshot_status"] == "superseded" and meta["superseded_at"]


def test_unknown_snapshot_returns_404(client):
    assert client.get("/api/dashboard?snapshot_id=snap-nope").status_code == 404
    assert client.get("/api/dataset/snapshots/snap-nope").status_code == 404


def test_failed_validation_does_not_replace_active_snapshot(client, monkeypatch):
    before = client.get("/api/dashboard").json()

    def broken_builder(ref, seed):
        ds = build_dataset(ref, seed)
        ds["spend"] = [r for r in ds["spend"] if r["service"] != "S3"]  # incomplete billing data
        return ds

    monkeypatch.setattr(snapshots, "build_dataset", broken_builder)
    res = _refresh(client, seed=99)
    assert res.status_code == 500
    detail = res.json()["detail"]
    assert detail["active_snapshot_id"] == before["snapshot_id"]
    assert detail["run"]["status"] == "failed" and "missing services" in detail["error"]
    assert client.get("/api/dashboard").json() == before
    assert _count("dataset_snapshots") == 1
    assert client.get("/api/dataset").json()["last_refresh"]["status"] == "failed"


def test_failure_mid_write_rolls_back_completely(client, monkeypatch):
    before = _active(client)
    rows = {t: _count(t) for t in ("dataset_snapshots", "billing_records", "resources", "utilization_metrics")}

    def explode(conn, snapshot_id, at):
        raise RuntimeError("disk full (simulated)")

    monkeypatch.setattr(snapshots, "_activate", explode)
    res = _refresh(client, seed=99)
    assert res.status_code == 500 and "disk full" in res.json()["detail"]["error"]
    assert _active(client) == before
    assert {t: _count(t) for t in rows} == rows  # nothing from the failed snapshot was left behind


def test_concurrent_refresh_is_rejected(client):
    assert snapshots._refresh_lock.acquire(blocking=False)
    try:
        assert _refresh(client, seed=99).status_code == 409
    finally:
        snapshots._refresh_lock.release()


def test_refresh_rejects_future_reference_date(client):
    assert _refresh(client, reference_date="2999-01-01").status_code == 422


def test_interrupted_runs_are_marked_failed(client):
    with closing(sqlite3.connect(db.db_path())) as c:
        c.execute("INSERT INTO refresh_runs (trigger, status, started_at) VALUES ('manual', 'running', '2026-01-01T00:00:00Z')")
        c.commit()
    assert snapshots.mark_interrupted_runs() == 1
    assert client.get("/api/dataset/refresh-history").json()[0]["status"] == "failed"


def test_validation_catches_bad_data():
    ds = build_dataset(date(2026, 11, 9))
    assert validate_dataset(ds) == []
    bad = build_dataset(date(2026, 11, 9))
    bad["spend"][0]["cost"] = -5
    assert any("invalid cost" in e for e in validate_dataset(bad))
    dup = build_dataset(date(2026, 11, 9))
    dup["resources"].append(dict(dup["resources"][0]))
    assert any("unique" in e for e in validate_dataset(dup))


# ------------------------------------------------------ no mixed snapshot reads ---

def test_refresh_during_a_request_cannot_mix_snapshots(client, monkeypatch):
    before = _active(client)
    real = main_module.scored_recommendations
    fired = []

    def refresh_then_score(ds):
        if not fired:
            fired.append(snapshots.refresh("test", seed=99)["snapshot"]["snapshot_id"])
        return real(ds)

    monkeypatch.setattr(main_module, "scored_recommendations", refresh_then_score)
    res = client.post("/api/copilot", json={"question": "What should I investigate first?"})
    assert fired and fired[0] != before
    assert res.headers["X-Snapshot-Id"] == before == res.json()["snapshot_id"]
    recs = client.get(f"/api/recommendations?snapshot_id={before}")
    assert {r["snapshot_id"] for r in recs.json()} == {before}


def test_concurrent_reads_during_refreshes_are_never_mixed(client):
    errors, stop = [], threading.Event()

    def reader():
        while not stop.is_set():
            ds = snapshots.load_dataset()
            if content_hash(ds["seed"], ds["spend"], ds["resources"]) != ds["dataset_id"]:
                errors.append(ds["snapshot_id"])

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    try:
        for seed in (99, 17, 42, 7, 17):
            snapshots.refresh("test", seed=seed)
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert errors == []
    assert _count("dataset_snapshots") == 6


# ------------------------------------------------------------ date comparison ---

def test_comparison_uses_equivalent_full_month_windows(client):
    d = client.get("/api/dashboard").json()
    c = d["comparison"]
    assert c["basis"] == "full_calendar_month" and c["equivalent_windows"] is True
    assert c["current"]["period"] == d["month"]
    assert c["current"]["start"].endswith("-01") and c["previous"]["start"].endswith("-01")
    assert c["previous"]["total"] == d["previous_spend"] and c["current"]["total"] == d["total_spend"]
    expected = round((d["total_spend"] - d["previous_spend"]) / d["previous_spend"] * 100, 1)
    assert d["change_percent"] == expected


def test_comparison_across_year_boundary(client):
    _refresh(client, reference_date="2026-01-15")
    c = client.get("/api/dashboard").json()["comparison"]
    assert (c["current"]["period"], c["previous"]["period"]) == ("2026-01", "2025-12")
    assert (c["current"]["days"], c["previous"]["days"]) == (31, 31)
    assert c["equivalent_windows"] is True


# ------------------------------------------------------------------- freshness ---

def test_freshness_current_for_this_month(client):
    meta = client.get("/api/dataset").json()
    assert meta["freshness"]["status"] == "current"
    assert meta["created_at"] and meta["activated_at"] and meta["last_refresh"]["status"] == "created"


def test_freshness_stale_when_newer_month_exists(client):
    _refresh(client, reference_date="2026-01-15")
    meta = client.get("/api/dataset").json()
    assert meta["billing_period"]["current"] == "2026-01"
    assert meta["freshness"]["status"] == ("stale" if date.today() >= date(2026, 2, 1) else "current")


# ---------------------------------------------------------------- lifecycle link ---

def test_lifecycle_events_record_snapshot(client):
    sid = _active(client)
    rec = client.get("/api/recommendations").json()[0]
    client.post(f"/api/recommendations/{rec['id']}/actions", json={"action": "investigate"})
    assert client.get(f"/api/recommendations/{rec['id']}").json()["history"][0]["snapshot_id"] == sid
    anom = client.get("/api/anomalies").json()[0]
    client.post(f"/api/anomalies/{anom['id']}/actions", json={"action": "acknowledge"})
    assert client.get(f"/api/anomalies/{anom['id']}").json()["history"][0]["snapshot_id"] == sid


# ------------------------------------------------------------------- migrations ---

def _make_v1_database(path: Path):
    with closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TABLE feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, recommendation_id TEXT NOT NULL, "
                  "decision TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE recommendation_events (id INTEGER PRIMARY KEY AUTOINCREMENT, recommendation_id TEXT NOT NULL, "
                  "action TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL, reason TEXT, note TEXT, "
                  "snooze_until TEXT, ruleset_version TEXT, dataset_id TEXT, estimated_monthly_savings REAL, created_at TEXT)")
        c.execute("CREATE TABLE anomaly_events (id INTEGER PRIMARY KEY AUTOINCREMENT, anomaly_id TEXT NOT NULL, "
                  "action TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL, reason TEXT, note TEXT, "
                  "detector_version TEXT, dataset_id TEXT, created_at TEXT)")
        c.execute("INSERT INTO recommendation_events (recommendation_id, action, from_status, to_status) "
                  "VALUES ('rec-i-demo-01', 'investigate', 'open', 'investigating')")
        c.execute("INSERT INTO anomaly_events (anomaly_id, action, from_status, to_status, dataset_id) "
                  "VALUES ('anom-EC2-2026-11-spike', 'acknowledge', 'open', 'acknowledged', 'ds-old')")
        c.commit()


def test_migration_backs_up_and_preserves_existing_data(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    _make_v1_database(path)
    monkeypatch.setenv("DATABASE_PATH", str(path))
    result = db.init_db()
    assert result["applied"] == [1, 2] and result["backup_path"]
    with closing(sqlite3.connect(result["backup_path"])) as b:
        assert b.execute("SELECT COUNT(*) FROM anomaly_events").fetchone()[0] == 1
        backed_up = {r[0] for r in b.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert backed_up - {"sqlite_sequence"} == {"feedback", "recommendation_events", "anomaly_events"}
    with closing(sqlite3.connect(path)) as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"dataset_snapshots", "billing_records", "resources", "utilization_metrics",
                "refresh_runs", "schema_migrations"} <= tables
        row = c.execute("SELECT anomaly_id, dataset_id, snapshot_id FROM anomaly_events").fetchone()
        assert row == ("anom-EC2-2026-11-spike", "ds-old", None)
        assert c.execute("SELECT recommendation_id FROM recommendation_events").fetchone()[0] == "rec-i-demo-01"
    # Idempotent: a second start applies nothing and makes no new backup.
    assert db.init_db() == {"applied": [], "backup_path": None}
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_new_database_needs_no_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "fresh.db"))
    result = db.init_db()
    assert result == {"applied": [1, 2], "backup_path": None}
    assert [m["version"] for m in db.applied_migrations()] == [1, 2]
