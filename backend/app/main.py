import calendar
import os
from datetime import date
from typing import Literal, Optional
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from .engine import recommendations as scored_recommendations, anomalies as detect_anomalies, anomaly_history
from .db import SCHEMA_VERSION, applied_migrations, init_db, save_feedback, get_feedback, events_for, anomaly_events_for
from . import anomalies as anomaly_engine
from . import copilot as copilot_engine
from . import lifecycle
from . import snapshots
from .recommendations import scoring_model

load_dotenv()
app = FastAPI(title="CloudPilot AI API", version="2.1.0",
              description="Synthetic-data cloud cost intelligence portfolio MVP.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-Snapshot-Id", "X-Dataset-Id"],
)


@app.on_event("startup")
def startup():
    init_db()
    snapshots.mark_interrupted_runs()
    snapshots.ensure_active_snapshot()


# ---------------------------------------------------------------- one snapshot per request ---

def request_dataset(
    response: Response,
    snapshot_id: Optional[str] = Query(None, description="Read a specific snapshot instead of the active one."),
) -> dict:
    """Resolve the snapshot ONCE per request. Every calculation in the request uses this object,
    so a refresh that activates a new snapshot mid-request cannot produce a mixed response."""
    try:
        ds = snapshots.load_dataset(snapshot_id)
    except snapshots.SnapshotNotFound:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")
    response.headers["X-Snapshot-Id"] = ds["snapshot_id"]
    response.headers["X-Dataset-Id"] = ds["dataset_id"]
    return ds


Dataset = Depends(request_dataset)


class FeedbackIn(BaseModel):
    decision: Literal["accepted", "dismissed"]


class ActionIn(BaseModel):
    action: Literal["investigate", "plan", "implement", "snooze", "dismiss", "reopen"]
    reason: Optional[Literal[tuple(lifecycle.DISMISS_REASONS)]] = None  # type: ignore[valid-type]
    note: Optional[str] = Field(default=None, max_length=500)
    snooze_days: Optional[int] = Field(default=None, ge=1, le=90)


class AnomalyActionIn(BaseModel):
    action: Literal["acknowledge", "investigate", "resolve", "reopen"]
    resolution: Optional[Literal[tuple(anomaly_engine.RESOLUTIONS)]] = None  # type: ignore[valid-type]
    note: Optional[str] = Field(default=None, max_length=500)


class ChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class RefreshIn(BaseModel):
    reference_date: Optional[date] = Field(
        default=None, description="Billing month to generate (defaults to today). Cannot be in the future.")
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1,
                                description="Synthetic generator seed (defaults to the demo seed).")


def _tag(items: list[dict], ds: dict) -> list[dict]:
    return [x | {"snapshot_id": ds["snapshot_id"]} for x in items]


def _recs_with_status(ds: dict):
    return _tag(lifecycle.with_status(scored_recommendations(ds)), ds)


def _get_rec(ds: dict, recommendation_id: str):
    rec = next((r for r in _recs_with_status(ds) if r["id"] == recommendation_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


# ------------------------------------------------------------------------------- dataset ---

@app.get("/api/health")
def health(ds: dict = Dataset):
    return {"status": "ok", "data_mode": "synthetic_demo", "dataset_id": ds["dataset_id"],
            "snapshot_id": ds["snapshot_id"], "schema_version": SCHEMA_VERSION}


@app.get("/api/dataset")
def dataset(ds: dict = Dataset):
    """Metadata of the active (or requested) snapshot, including data freshness and the last refresh."""
    return snapshots.snapshot_meta(ds["snapshot_id"])


@app.get("/api/dataset/snapshots")
def dataset_snapshots(limit: int = Query(50, ge=1, le=200)):
    return {"active_snapshot_id": snapshots.active_snapshot_id(), "snapshots": snapshots.list_snapshots(limit)}


@app.get("/api/dataset/snapshots/{snapshot_id}")
def dataset_snapshot(snapshot_id: str):
    try:
        return snapshots.snapshot_meta(snapshot_id)
    except snapshots.SnapshotNotFound:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")


@app.get("/api/dataset/refresh-history")
def dataset_refresh_history(limit: int = Query(20, ge=1, le=200)):
    return snapshots.refresh_history(limit)


@app.get("/api/dataset/migrations")
def dataset_migrations():
    return {"schema_version": SCHEMA_VERSION, "applied": applied_migrations()}


@app.post("/api/dataset/refresh")
def refresh_dataset(payload: Optional[RefreshIn] = Body(default=None)):
    """Controlled refresh. 'created' activates a new snapshot; 'unchanged' keeps the active one when the
    regenerated data is identical; a failure keeps the last valid snapshot active (HTTP 500 with the run)."""
    payload = payload or RefreshIn()
    if payload.reference_date and payload.reference_date > date.today():
        raise HTTPException(status_code=422, detail="reference_date cannot be in the future")
    if payload.reference_date and payload.reference_date < date(2015, 1, 1):
        raise HTTPException(status_code=422, detail="reference_date must be 2015-01-01 or later")
    try:
        return snapshots.refresh("manual", payload.reference_date, payload.seed)
    except snapshots.RefreshInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except snapshots.RefreshFailed as e:
        raise HTTPException(status_code=500, detail={
            "message": "Refresh failed. The previous snapshot is still active.",
            "error": e.run.get("error"), "run": e.run, "active_snapshot_id": snapshots.active_snapshot_id()})


# ----------------------------------------------------------------------------- dashboard ---

def _window(month: str) -> dict:
    y, m = map(int, month.split("-"))
    days = calendar.monthrange(y, m)[1]
    return {"period": month, "start": f"{month}-01", "end": f"{month}-{days:02d}", "days": days}


def _previous_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _dashboard(ds: dict) -> dict:
    spend = ds["spend"]
    months = sorted({x["month"] for x in spend})
    latest = months[-1]
    previous = months[-2]
    current_total = round(sum(x["cost"] for x in spend if x["month"] == latest), 2)
    previous_total = round(sum(x["cost"] for x in spend if x["month"] == previous), 2)
    change = round((current_total - previous_total) / previous_total * 100, 1) if previous_total else 0
    by_service = {x["service"]: x["cost"] for x in spend if x["month"] == latest}
    cur_w, prev_w = _window(latest), _window(previous)
    services_cur = {x["service"] for x in spend if x["month"] == latest}
    services_prev = {x["service"] for x in spend if x["month"] == previous}
    return {
        "month": latest, "total_spend": current_total, "previous_spend": previous_total,
        "change_percent": change, "service_breakdown": by_service,
        "monthly_trend": [
            {"month": m, "total": round(sum(x["cost"] for x in spend if x["month"] == m), 2)}
            for m in months
        ],
        "comparison": {
            "basis": "full_calendar_month",
            "current": cur_w | {"total": current_total, "daily_average": round(current_total / cur_w["days"], 2)},
            "previous": prev_w | {"total": previous_total, "daily_average": round(previous_total / prev_w["days"], 2)},
            "equivalent_windows": previous == _previous_month(latest) and services_cur == services_prev,
            "note": "Synthetic data models every month, including the current one, as a complete calendar month, "
                    "so both periods cover their full month and the same services.",
        },
        "data_mode": ds["data_source_label"],
        "dataset_id": ds["dataset_id"],
        "snapshot_id": ds["snapshot_id"],
        "generated_at": ds["generated_at"],
    }


@app.get("/api/dashboard")
def dashboard(ds: dict = Dataset):
    return _dashboard(ds)


@app.get("/api/spend")
def spend(ds: dict = Dataset):
    return ds["spend"]


@app.get("/api/resources")
def resources(ds: dict = Dataset):
    return ds["resources"]


# ----------------------------------------------------------------------- recommendations ---

@app.get("/api/recommendations")
def get_recommendations(ds: dict = Dataset):
    return _recs_with_status(ds)


@app.get("/api/recommendations/model")
def get_scoring_model():
    return scoring_model() | {"statuses": lifecycle.STATUSES, "dismiss_reasons": lifecycle.DISMISS_REASONS}


@app.get("/api/recommendations/analytics")
def get_recommendation_analytics(ds: dict = Dataset):
    return lifecycle.analytics(_recs_with_status(ds))


@app.get("/api/recommendations/{recommendation_id}")
def get_recommendation(recommendation_id: str, ds: dict = Dataset):
    rec = _get_rec(ds, recommendation_id)
    return rec | {"history": events_for(recommendation_id)}


@app.post("/api/recommendations/{recommendation_id}/actions")
def recommendation_action(recommendation_id: str, payload: ActionIn, ds: dict = Dataset):
    rec = _get_rec(ds, recommendation_id)
    try:
        lifecycle.apply_action(rec, payload.action, payload.reason, payload.note, payload.snooze_days)
    except lifecycle.TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_rec(ds, recommendation_id) | {"history": events_for(recommendation_id)}


# ----------------------------------------------------------------------------- anomalies ---

def _anomalies_with_status(ds: dict):
    return _tag(anomaly_engine.with_status(detect_anomalies(ds)), ds)


def _get_anomaly(ds: dict, anomaly_id: str):
    a = next((x for x in _tag(anomaly_engine.with_status(anomaly_history(ds)), ds) if x["id"] == anomaly_id), None)
    if not a:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return a


def _anomaly_detail(ds: dict, anomaly_id: str):
    a = _get_anomaly(ds, anomaly_id)
    return a | {
        "investigation": anomaly_engine.investigation(a, ds, _recs_with_status(ds)),
        "history": anomaly_events_for(anomaly_id),
    }


@app.get("/api/anomalies")
def get_anomalies(ds: dict = Dataset):
    """Anomalies detected in the latest billing month, most severe first."""
    return _anomalies_with_status(ds)


@app.get("/api/anomalies/history")
def get_anomaly_history(ds: dict = Dataset):
    history = _tag(anomaly_engine.with_status(anomaly_history(ds)), ds)
    return {"anomalies": history, "summary": anomaly_engine.summary(history),
            "dataset_id": ds["dataset_id"], "snapshot_id": ds["snapshot_id"]}


@app.get("/api/anomalies/config")
def get_anomaly_config():
    return {"version": anomaly_engine.DETECTOR_VERSION, "thresholds": anomaly_engine.CONFIG,
            "types": anomaly_engine.TYPE_LABELS, "statuses": anomaly_engine.STATUSES,
            "resolutions": anomaly_engine.RESOLUTIONS,
            "note": "Example thresholds. They are not yet user-configurable."}


@app.get("/api/anomalies/{anomaly_id}")
def get_anomaly(anomaly_id: str, ds: dict = Dataset):
    return _anomaly_detail(ds, anomaly_id)


@app.post("/api/anomalies/{anomaly_id}/actions")
def anomaly_action(anomaly_id: str, payload: AnomalyActionIn, ds: dict = Dataset):
    a = _get_anomaly(ds, anomaly_id)
    try:
        anomaly_engine.apply_action(a, payload.action, payload.resolution, payload.note)
    except anomaly_engine.TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _anomaly_detail(ds, anomaly_id)


# ------------------------------------------------------------------------- v1 + copilot ---

@app.post("/api/recommendations/{recommendation_id}/feedback")
def feedback(recommendation_id: str, payload: FeedbackIn, ds: dict = Dataset):
    """v1 endpoint, kept for compatibility. Maps onto the lifecycle actions."""
    rec = _get_rec(ds, recommendation_id)
    try:
        if payload.decision == "accepted":
            lifecycle.apply_action(rec, "investigate")
        else:
            lifecycle.apply_action(rec, "dismiss", "other", "Dismissed via v1 feedback endpoint")
    except lifecycle.TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    row_id = save_feedback(recommendation_id, payload.decision)
    return {"id": row_id, "recommendation_id": recommendation_id, "decision": payload.decision}


@app.get("/api/feedback")
def feedback_history():
    return get_feedback()


@app.post("/api/copilot")
def copilot(payload: ChatIn, ds: dict = Dataset):
    body = copilot_engine.answer(
        payload.question.strip(), _dashboard(ds), _recs_with_status(ds), _anomalies_with_status(ds), ds["dataset_id"]
    )
    return body | {"snapshot_id": ds["snapshot_id"]}


@app.get("/")
def root():
    return {"message": "CloudPilot AI API. Visit /docs for API documentation."}
