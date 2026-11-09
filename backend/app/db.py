import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SCHEMA_VERSION = 2


def db_path() -> str:
    # Read at call time so tests (and deployments) can point at a different file.
    return os.getenv("DATABASE_PATH", "./cloudpilot.db")


def connect(autocommit: bool = False):
    """Open a connection. ``autocommit=True`` lets the caller manage BEGIN/COMMIT explicitly."""
    path = db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None if autocommit else "")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------- migrations ---
# Additive only: migrations create tables, indexes and nullable columns. They never
# drop, rename or rewrite existing data. Each runs once and is recorded in
# schema_migrations.

def _migration_1_baseline(conn):
    """Pre-Sprint-1 schema: v1 feedback plus the lifecycle event logs."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # Append-only audit log. A recommendation's current status is its latest event.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS recommendation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id TEXT NOT NULL,
        action TEXT NOT NULL,
        from_status TEXT NOT NULL,
        to_status TEXT NOT NULL,
        reason TEXT,
        note TEXT,
        snooze_until TEXT,
        ruleset_version TEXT,
        dataset_id TEXT,
        estimated_monthly_savings REAL,
        created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rec_events ON recommendation_events(recommendation_id, id)")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS anomaly_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anomaly_id TEXT NOT NULL,
        action TEXT NOT NULL,
        from_status TEXT NOT NULL,
        to_status TEXT NOT NULL,
        reason TEXT,
        note TEXT,
        detector_version TEXT,
        dataset_id TEXT,
        created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anom_events ON anomaly_events(anomaly_id, id)")
    _migrate_v1_feedback(conn)


def _migration_2_snapshots(conn):
    """Sprint 1: persisted dataset snapshots, their records, and refresh history."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS dataset_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
        data_source TEXT NOT NULL,
        data_source_label TEXT NOT NULL,
        scenario_id TEXT NOT NULL,
        scenario_json TEXT NOT NULL,
        seed INTEGER NOT NULL,
        generator_version TEXT NOT NULL,
        reference_date TEXT NOT NULL,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        spend_rows INTEGER NOT NULL,
        resource_count INTEGER NOT NULL,
        total_cost REAL NOT NULL,
        created_at TEXT NOT NULL,
        activated_at TEXT NOT NULL,
        superseded_at TEXT
    )
    """)
    # At most one active snapshot, enforced by the database itself.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_snapshot "
                 "ON dataset_snapshots(status) WHERE status = 'active'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_dataset ON dataset_snapshots(dataset_id)")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS billing_records (
        snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(snapshot_id),
        month TEXT NOT NULL,
        service TEXT NOT NULL,
        cost REAL NOT NULL CHECK (cost >= 0),
        PRIMARY KEY (snapshot_id, month, service)
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS resources (
        snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(snapshot_id),
        resource_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        service TEXT NOT NULL,
        type TEXT,
        region TEXT,
        environment TEXT,
        owner_team TEXT,
        status TEXT,
        monthly_cost REAL NOT NULL CHECK (monthly_cost >= 0),
        observation_days INTEGER,
        metrics_age_days INTEGER,
        attributes_json TEXT NOT NULL,
        PRIMARY KEY (snapshot_id, resource_id)
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS utilization_metrics (
        snapshot_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        metric TEXT NOT NULL,
        value REAL,
        value_type TEXT NOT NULL CHECK (value_type IN ('integer', 'number', 'boolean', 'missing')),
        PRIMARY KEY (snapshot_id, resource_id, metric),
        FOREIGN KEY (snapshot_id, resource_id) REFERENCES resources(snapshot_id, resource_id)
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS refresh_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running', 'created', 'unchanged', 'failed')),
        requested_reference_date TEXT,
        requested_seed INTEGER,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        previous_snapshot_id TEXT,
        snapshot_id TEXT,
        dataset_id TEXT,
        error TEXT
    )
    """)
    # Link lifecycle decisions to the snapshot they were made on. Nullable: older rows predate snapshots.
    for table in ("recommendation_events", "anomaly_events"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "snapshot_id" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN snapshot_id TEXT")


MIGRATIONS = [
    (1, "baseline", _migration_1_baseline),
    (2, "sprint1_dataset_snapshots", _migration_2_snapshots),
]


def backup_database(label: str) -> str | None:
    """Consistent copy via SQLite's online backup API. Returns its path, or None if there is nothing to back up."""
    path = Path(db_path())
    if not path.exists() or path.stat().st_size == 0:
        return None
    target_dir = path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = target_dir / f"{path.stem}-{label}-{stamp}.db"
    with closing(sqlite3.connect(path)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(f"backup {target} failed its integrity check")
    return str(target)


def applied_migrations() -> list[dict]:
    with closing(connect()) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'schema_migrations'").fetchone():
            return []
        return [dict(r) for r in conn.execute("SELECT * FROM schema_migrations ORDER BY version")]


def init_db() -> dict:
    """Bring the schema up to SCHEMA_VERSION, backing up an existing database before any change."""
    with closing(connect(autocommit=True)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")  # readers keep working while a refresh writes
        user_tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
        done = set()
        if "schema_migrations" in user_tables:
            done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        pending = [m for m in MIGRATIONS if m[0] not in done]
        backup = None
        if pending and user_tables:
            # Existing data is about to see a schema change: keep a restorable copy before writing anything.
            backup = backup_database(f"pre-migration-v{pending[-1][0]}")
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL, backup_path TEXT)""")
        for version, name, migrate in pending:
            conn.execute("BEGIN IMMEDIATE")
            try:
                migrate(conn)
                conn.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at, backup_path) VALUES (?, ?, ?, ?)",
                    (version, name, _now(), backup))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return {"applied": [v for v, _, _ in pending], "backup_path": backup}


def _migrate_v1_feedback(conn):
    """One-time carry-over of v1 accept/dismiss feedback into the lifecycle log."""
    if conn.execute("SELECT 1 FROM recommendation_events LIMIT 1").fetchone():
        return
    rows = conn.execute("""
        SELECT recommendation_id, decision, created_at FROM feedback f
        WHERE id = (SELECT MAX(id) FROM feedback WHERE recommendation_id = f.recommendation_id)
    """).fetchall()
    for r in rows:
        accepted = r["decision"] == "accepted"
        conn.execute(
            """INSERT INTO recommendation_events
               (recommendation_id, action, from_status, to_status, reason, note, ruleset_version, created_at)
               VALUES (?, ?, 'open', ?, ?, 'Migrated from v1 feedback', '1.0.0', ?)""",
            (r["recommendation_id"], "investigate" if accepted else "dismiss",
             "investigating" if accepted else "dismissed", None if accepted else "other",
             str(r["created_at"]).replace(" ", "T") + "Z"),
        )


# ------------------------------------------------------------- v1 feedback ---

def save_feedback(recommendation_id: str, decision: str):
    with closing(connect()) as conn:
        cur = conn.execute(
            "INSERT INTO feedback(recommendation_id, decision) VALUES (?, ?)",
            (recommendation_id, decision)
        )
        conn.commit()
        return cur.lastrowid


def get_feedback():
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM feedback ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------ lifecycle events ---

def record_event(**event) -> dict:
    cols = ["recommendation_id", "action", "from_status", "to_status", "reason", "note",
            "snooze_until", "ruleset_version", "dataset_id", "estimated_monthly_savings", "snapshot_id"]
    with closing(connect()) as conn:
        cur = conn.execute(
            f"INSERT INTO recommendation_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [event.get(c) for c in cols],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM recommendation_events WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def latest_events() -> dict[str, dict]:
    with closing(connect()) as conn:
        rows = conn.execute("""
            SELECT * FROM recommendation_events e
            WHERE id = (SELECT MAX(id) FROM recommendation_events WHERE recommendation_id = e.recommendation_id)
        """).fetchall()
        return {r["recommendation_id"]: dict(r) for r in rows}


def events_for(recommendation_id: str | None = None) -> list[dict]:
    with closing(connect()) as conn:
        if recommendation_id:
            rows = conn.execute(
                "SELECT * FROM recommendation_events WHERE recommendation_id = ? ORDER BY id DESC",
                (recommendation_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM recommendation_events ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


# -------------------------------------------------------- anomaly events ---

def record_anomaly_event(**event) -> dict:
    cols = ["anomaly_id", "action", "from_status", "to_status", "reason", "note", "detector_version",
            "dataset_id", "snapshot_id"]
    with closing(connect()) as conn:
        cur = conn.execute(
            f"INSERT INTO anomaly_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [event.get(c) for c in cols],
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM anomaly_events WHERE id = ?", (cur.lastrowid,)).fetchone())


def latest_anomaly_events() -> dict[str, dict]:
    with closing(connect()) as conn:
        rows = conn.execute("""
            SELECT * FROM anomaly_events e
            WHERE id = (SELECT MAX(id) FROM anomaly_events WHERE anomaly_id = e.anomaly_id)
        """).fetchall()
        return {r["anomaly_id"]: dict(r) for r in rows}


def anomaly_events_for(anomaly_id: str) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM anomaly_events WHERE anomaly_id = ? ORDER BY id DESC",
                            (anomaly_id,)).fetchall()
        return [dict(r) for r in rows]
