import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def db_path() -> str:
    # Read at call time so tests (and deployments) can point at a different file.
    return os.getenv("DATABASE_PATH", "./cloudpilot.db")


def connect():
    path = db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
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
        conn.commit()


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
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO feedback(recommendation_id, decision) VALUES (?, ?)",
            (recommendation_id, decision)
        )
        conn.commit()
        return cur.lastrowid


def get_feedback():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM feedback ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------ lifecycle events ---

def record_event(**event) -> dict:
    cols = ["recommendation_id", "action", "from_status", "to_status", "reason", "note",
            "snooze_until", "ruleset_version", "dataset_id", "estimated_monthly_savings"]
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO recommendation_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [event.get(c) for c in cols],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM recommendation_events WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def latest_events() -> dict[str, dict]:
    with connect() as conn:
        rows = conn.execute("""
            SELECT * FROM recommendation_events e
            WHERE id = (SELECT MAX(id) FROM recommendation_events WHERE recommendation_id = e.recommendation_id)
        """).fetchall()
        return {r["recommendation_id"]: dict(r) for r in rows}


def events_for(recommendation_id: str | None = None) -> list[dict]:
    with connect() as conn:
        if recommendation_id:
            rows = conn.execute(
                "SELECT * FROM recommendation_events WHERE recommendation_id = ? ORDER BY id DESC",
                (recommendation_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM recommendation_events ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


# -------------------------------------------------------- anomaly events ---

def record_anomaly_event(**event) -> dict:
    cols = ["anomaly_id", "action", "from_status", "to_status", "reason", "note", "detector_version", "dataset_id"]
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO anomaly_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [event.get(c) for c in cols],
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM anomaly_events WHERE id = ?", (cur.lastrowid,)).fetchone())


def latest_anomaly_events() -> dict[str, dict]:
    with connect() as conn:
        rows = conn.execute("""
            SELECT * FROM anomaly_events e
            WHERE id = (SELECT MAX(id) FROM anomaly_events WHERE anomaly_id = e.anomaly_id)
        """).fetchall()
        return {r["anomaly_id"]: dict(r) for r in rows}


def anomaly_events_for(anomaly_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM anomaly_events WHERE anomaly_id = ? ORDER BY id DESC", (anomaly_id,)).fetchall()
        return [dict(r) for r in rows]
