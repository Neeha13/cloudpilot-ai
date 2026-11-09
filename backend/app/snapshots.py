"""Persisted dataset snapshots: the single source of truth for every API.

Lifecycle of a refresh (``refresh()``):

1. A ``refresh_runs`` row is written as ``running``.
2. A dataset is generated and validated (``dataset.validate_dataset``).
3. If its content (``dataset_id``) equals the active snapshot's, nothing is written
   and the run is recorded as ``unchanged``.
4. Otherwise, inside ONE ``BEGIN IMMEDIATE`` transaction: the snapshot and all its
   billing, resource and utilization rows are inserted, read back and re-hashed,
   the previous snapshot is marked ``superseded`` and the new one ``active``.
   Any error rolls the whole transaction back, so the last valid snapshot stays
   active, and the run is recorded as ``failed`` with the error.

Reads (``load_dataset``) resolve one snapshot_id and return that snapshot only.
Snapshots are immutable once written, so they are cached by snapshot_id; a
request therefore can never combine rows from two snapshots.
"""
from __future__ import annotations

import copy
import json
import secrets
import threading
from collections import OrderedDict
from contextlib import closing
from datetime import date, datetime, timezone

from . import db
from .dataset import (
    SCENARIO, SEED, DatasetValidationError, build_dataset, content_hash, validate_dataset,
)

_CORE_RESOURCE_FIELDS = ("id", "service", "type", "region", "environment", "owner_team", "status",
                         "monthly_cost", "observation_days", "metrics_age_days", "metrics")

_refresh_lock = threading.Lock()
_cache: "OrderedDict[str, dict]" = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_SIZE = 8


class SnapshotNotFound(LookupError):
    pass


class RefreshInProgress(RuntimeError):
    pass


class RefreshFailed(RuntimeError):
    def __init__(self, message: str, run: dict):
        super().__init__(message)
        self.run = run


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_snapshot_id() -> str:
    return f"snap-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


# ------------------------------------------------------------------ writing ---

def _metric_row(value) -> tuple[float | None, str]:
    if value is None:
        return None, "missing"
    if isinstance(value, bool):
        return float(value), "boolean"
    if isinstance(value, int):
        return float(value), "integer"
    return float(value), "number"


def _insert_snapshot(conn, snapshot_id: str, ds: dict, created_at: str) -> None:
    months = sorted({r["month"] for r in ds["spend"]})
    total = round(sum(r["cost"] for r in ds["spend"] if r["month"] == months[-1]), 2)
    conn.execute(
        """INSERT INTO dataset_snapshots (snapshot_id, dataset_id, status, data_source, data_source_label,
               scenario_id, scenario_json, seed, generator_version, reference_date, period_start, period_end,
               spend_rows, resource_count, total_cost, created_at, activated_at)
           VALUES (?, ?, 'superseded', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (snapshot_id, ds["dataset_id"], ds["data_source"], ds["data_source_label"], ds["scenario"]["id"],
         json.dumps(ds["scenario"]), ds["seed"], ds["generator_version"], ds["reference_date"],
         months[0], months[-1], len(ds["spend"]), len(ds["resources"]), total, created_at, created_at),
    )
    conn.executemany(
        "INSERT INTO billing_records (snapshot_id, month, service, cost) VALUES (?, ?, ?, ?)",
        [(snapshot_id, r["month"], r["service"], r["cost"]) for r in ds["spend"]],
    )
    for pos, res in enumerate(ds["resources"]):
        extra = {k: v for k, v in res.items() if k not in _CORE_RESOURCE_FIELDS}
        conn.execute(
            """INSERT INTO resources (snapshot_id, resource_id, position, service, type, region, environment,
                   owner_team, status, monthly_cost, observation_days, metrics_age_days, attributes_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (snapshot_id, res["id"], pos, res["service"], res.get("type"), res.get("region"),
             res.get("environment"), res.get("owner_team"), res.get("status"), res["monthly_cost"],
             res.get("observation_days"), res.get("metrics_age_days"), json.dumps(extra, sort_keys=True)),
        )
        conn.executemany(
            """INSERT INTO utilization_metrics (snapshot_id, resource_id, position, metric, value, value_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(snapshot_id, res["id"], i, name, *_metric_row(v)) for i, (name, v) in enumerate(res["metrics"].items())],
        )


def _activate(conn, snapshot_id: str, at: str) -> str | None:
    prev = conn.execute("SELECT snapshot_id FROM dataset_snapshots WHERE status = 'active'").fetchone()
    if prev:
        conn.execute("UPDATE dataset_snapshots SET status = 'superseded', superseded_at = ? WHERE snapshot_id = ?",
                     (at, prev["snapshot_id"]))
    conn.execute("UPDATE dataset_snapshots SET status = 'active', activated_at = ?, superseded_at = NULL "
                 "WHERE snapshot_id = ?", (at, snapshot_id))
    return prev["snapshot_id"] if prev else None


# ------------------------------------------------------------------ reading ---

def _metric_value(value, kind):
    if kind == "missing":
        return None
    if kind == "boolean":
        return bool(value)
    if kind == "integer":
        return int(value)
    return value


def _read_snapshot(conn, snapshot_id: str) -> dict:
    row = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
    if not row:
        raise SnapshotNotFound(snapshot_id)
    spend = [dict(r) for r in conn.execute(
        "SELECT month, service, cost FROM billing_records WHERE snapshot_id = ? ORDER BY rowid", (snapshot_id,))]
    metrics: dict[str, dict] = {}
    for m in conn.execute("SELECT resource_id, metric, value, value_type FROM utilization_metrics "
                          "WHERE snapshot_id = ? ORDER BY resource_id, position", (snapshot_id,)):
        metrics.setdefault(m["resource_id"], {})[m["metric"]] = _metric_value(m["value"], m["value_type"])
    resources = []
    for r in conn.execute("SELECT * FROM resources WHERE snapshot_id = ? ORDER BY position", (snapshot_id,)):
        res = {"id": r["resource_id"], "service": r["service"], "type": r["type"], "region": r["region"],
               "environment": r["environment"], "owner_team": r["owner_team"], "status": r["status"],
               "monthly_cost": r["monthly_cost"]}
        res |= json.loads(r["attributes_json"])
        res |= {"metrics": metrics.get(r["resource_id"], {}), "observation_days": r["observation_days"],
                "metrics_age_days": r["metrics_age_days"]}
        resources.append(res)
    if content_hash(row["seed"], spend, resources, row["scenario_id"]) != row["dataset_id"]:
        raise RuntimeError(f"snapshot {snapshot_id} failed its integrity check (content hash mismatch)")
    return {
        "snapshot_id": snapshot_id,
        "dataset_id": row["dataset_id"],
        "snapshot_status": row["status"],
        "seed": row["seed"],
        "generator_version": row["generator_version"],
        "reference_date": row["reference_date"],
        "scenario": json.loads(row["scenario_json"]),
        "data_source": row["data_source"],
        "data_source_label": row["data_source_label"],
        # Kept for compatibility: "generated_at" is when this snapshot's data was produced.
        "generated_at": row["created_at"],
        "created_at": row["created_at"],
        "activated_at": row["activated_at"],
        "superseded_at": row["superseded_at"],
        "billing_period": {"start": row["period_start"], "end": row["period_end"], "current": row["period_end"]},
        "spend": spend,
        "resources": resources,
    }


def active_snapshot_id() -> str | None:
    with closing(db.connect()) as conn:
        row = conn.execute("SELECT snapshot_id FROM dataset_snapshots WHERE status = 'active'").fetchone()
        return row["snapshot_id"] if row else None


def _cached(snapshot_id: str) -> dict:
    with _cache_lock:
        if snapshot_id in _cache:
            _cache.move_to_end(snapshot_id)
            return _cache[snapshot_id]
    with closing(db.connect()) as conn:
        snap = _read_snapshot(conn, snapshot_id)
    # Status/superseded_at can change later; they are refreshed on every read in load_dataset().
    with _cache_lock:
        _cache[snapshot_id] = snap
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return snap


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def load_dataset(snapshot_id: str | None = None) -> dict:
    """Deep copy of one snapshot: the given one, or the active one (bootstrapping if none exists)."""
    sid = snapshot_id or active_snapshot_id()
    if sid is None:
        ensure_active_snapshot()
        sid = active_snapshot_id()
    snap = copy.deepcopy(_cached(sid))
    with closing(db.connect()) as conn:
        row = conn.execute("SELECT status, activated_at, superseded_at FROM dataset_snapshots WHERE snapshot_id = ?",
                           (sid,)).fetchone()
    snap.update(snapshot_status=row["status"], activated_at=row["activated_at"], superseded_at=row["superseded_at"])
    return snap


# ------------------------------------------------------------------ refresh ---

def _start_run(trigger: str, reference_date: date | None, seed: int | None) -> int:
    with closing(db.connect()) as conn:
        cur = conn.execute(
            "INSERT INTO refresh_runs (trigger, status, requested_reference_date, requested_seed, started_at) "
            "VALUES (?, 'running', ?, ?, ?)",
            (trigger, reference_date.isoformat() if reference_date else None, seed, _now()))
        conn.commit()
        return cur.lastrowid


def _finish_run(run_id: int, **fields) -> dict:
    fields["finished_at"] = _now()
    with closing(db.connect()) as conn:
        conn.execute(f"UPDATE refresh_runs SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     [*fields.values(), run_id])
        conn.commit()
        return dict(conn.execute("SELECT * FROM refresh_runs WHERE id = ?", (run_id,)).fetchone())


def refresh(trigger: str = "manual", reference_date: date | None = None, seed: int | None = None,
            _builder=None) -> dict:
    """Generate, validate and atomically activate a new snapshot. See module docstring."""
    if not _refresh_lock.acquire(blocking=False):
        raise RefreshInProgress("A dataset refresh is already running.")
    try:
        run_id = _start_run(trigger, reference_date, seed)
        previous = active_snapshot_id()
        try:
            ds = (_builder or build_dataset)(reference_date, seed if seed is not None else SEED)
            errors = validate_dataset(ds)
            if errors:
                raise DatasetValidationError(errors)
            if previous and _cached(previous)["dataset_id"] == ds["dataset_id"]:
                run = _finish_run(run_id, status="unchanged", previous_snapshot_id=previous,
                                  snapshot_id=previous, dataset_id=ds["dataset_id"])
                return {"status": "unchanged", "run": run, "snapshot": snapshot_meta(previous)}
            snapshot_id, now = _new_snapshot_id(), _now()
            with closing(db.connect(autocommit=True)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _insert_snapshot(conn, snapshot_id, ds, now)
                    # Read back inside the transaction: what is stored must hash to the same dataset_id.
                    _read_snapshot(conn, snapshot_id)
                    previous = _activate(conn, snapshot_id, now)
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            run = _finish_run(run_id, status="created", previous_snapshot_id=previous,
                              snapshot_id=snapshot_id, dataset_id=ds["dataset_id"])
            return {"status": "created", "run": run, "snapshot": snapshot_meta(snapshot_id)}
        except Exception as e:
            run = _finish_run(run_id, status="failed", previous_snapshot_id=previous, snapshot_id=None,
                              error=f"{type(e).__name__}: {e}"[:1000])
            raise RefreshFailed(str(e), run) from e
    finally:
        _refresh_lock.release()


def ensure_active_snapshot() -> dict | None:
    """Create the first snapshot if the database has none. Existing snapshots are never replaced here."""
    if active_snapshot_id():
        return None
    try:
        return refresh(trigger="bootstrap")
    except RefreshInProgress:
        with _refresh_lock:  # another thread is bootstrapping; wait for it
            return None


def mark_interrupted_runs() -> int:
    """Runs left 'running' by a crashed process are recorded as failed on startup."""
    with closing(db.connect()) as conn:
        cur = conn.execute("UPDATE refresh_runs SET status = 'failed', finished_at = ?, "
                           "error = 'Interrupted: the server stopped before the refresh finished' "
                           "WHERE status = 'running'", (_now(),))
        conn.commit()
        return cur.rowcount


# ----------------------------------------------------------------- metadata ---

def freshness(snap: dict, today: date | None = None) -> dict:
    today = today or date.today()
    current = today.strftime("%Y-%m")
    period = snap["billing_period"]["current"]
    if period < current:
        return {"status": "stale", "current_calendar_month": current,
                "message": f"Data covers up to {period}. A newer billing month ({current}) is available; refresh to load it."}
    return {"status": "current", "current_calendar_month": current,
            "message": f"Data covers the current billing month ({period})."}


def refresh_history(limit: int = 20) -> list[dict]:
    with closing(db.connect()) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM refresh_runs ORDER BY id DESC LIMIT ?", (limit,))]


def list_snapshots(limit: int = 50) -> list[dict]:
    with closing(db.connect()) as conn:
        rows = conn.execute(
            """SELECT snapshot_id, dataset_id, status, seed, generator_version, reference_date, period_start,
                      period_end, spend_rows, resource_count, total_cost, created_at, activated_at, superseded_at
               FROM dataset_snapshots ORDER BY created_at DESC, rowid DESC LIMIT ?""", (limit,))
        return [dict(r) for r in rows]


def snapshot_meta(snapshot_id: str | None = None) -> dict:
    snap = load_dataset(snapshot_id)
    history = refresh_history(1)
    return {k: v for k, v in snap.items() if k not in ("spend", "resources")} | {
        "resource_count": len(snap["resources"]),
        "spend_rows": len(snap["spend"]),
        "freshness": freshness(snap),
        "last_refresh": history[0] if history else None,
    }


__all__ = ["SCENARIO", "load_dataset", "refresh", "snapshot_meta", "list_snapshots", "refresh_history",
           "ensure_active_snapshot", "active_snapshot_id", "freshness", "SnapshotNotFound",
           "RefreshInProgress", "RefreshFailed"]
