import os
from typing import Literal, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from .dataset import dataset_meta, get_dataset
from .engine import recommendations as scored_recommendations, anomalies as detect_anomalies, anomaly_history
from .db import init_db, save_feedback, get_feedback, events_for, anomaly_events_for
from . import anomalies as anomaly_engine
from . import copilot as copilot_engine
from . import lifecycle
from .recommendations import scoring_model

load_dotenv()
app = FastAPI(title="CloudPilot AI API", version="2.0.0",
              description="Synthetic-data cloud cost intelligence portfolio MVP.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.on_event("startup")
def startup():
    init_db()


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


def _recs_with_status(dataset=None):
    return lifecycle.with_status(scored_recommendations(dataset))


def _get_rec(recommendation_id: str):
    rec = next((r for r in _recs_with_status() if r["id"] == recommendation_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


@app.get("/api/health")
def health():
    return {"status": "ok", "data_mode": "synthetic_demo", "dataset_id": dataset_meta()["dataset_id"]}


@app.get("/api/dataset")
def dataset():
    return dataset_meta()


@app.get("/api/dashboard")
def dashboard():
    ds = get_dataset()
    spend = ds["spend"]
    months = sorted({x["month"] for x in spend})
    latest = months[-1]
    previous = months[-2]
    current_total = round(sum(x["cost"] for x in spend if x["month"] == latest), 2)
    previous_total = round(sum(x["cost"] for x in spend if x["month"] == previous), 2)
    change = round((current_total - previous_total) / previous_total * 100, 1) if previous_total else 0
    by_service = {x["service"]: x["cost"] for x in spend if x["month"] == latest}
    return {
        "month": latest, "total_spend": current_total, "previous_spend": previous_total,
        "change_percent": change, "service_breakdown": by_service,
        "monthly_trend": [
            {"month": m, "total": round(sum(x["cost"] for x in spend if x["month"] == m), 2)}
            for m in months
        ],
        "data_mode": ds["data_source_label"],
        "dataset_id": ds["dataset_id"],
        "generated_at": ds["generated_at"],
    }


@app.get("/api/spend")
def spend():
    return get_dataset()["spend"]


@app.get("/api/resources")
def resources():
    return get_dataset()["resources"]


@app.get("/api/recommendations")
def get_recommendations():
    return _recs_with_status()


@app.get("/api/recommendations/model")
def get_scoring_model():
    return scoring_model() | {"statuses": lifecycle.STATUSES, "dismiss_reasons": lifecycle.DISMISS_REASONS}


@app.get("/api/recommendations/analytics")
def get_recommendation_analytics():
    return lifecycle.analytics(_recs_with_status())


@app.get("/api/recommendations/{recommendation_id}")
def get_recommendation(recommendation_id: str):
    rec = _get_rec(recommendation_id)
    return rec | {"history": events_for(recommendation_id)}


@app.post("/api/recommendations/{recommendation_id}/actions")
def recommendation_action(recommendation_id: str, payload: ActionIn):
    rec = _get_rec(recommendation_id)
    try:
        lifecycle.apply_action(rec, payload.action, payload.reason, payload.note, payload.snooze_days)
    except lifecycle.TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_rec(recommendation_id) | {"history": events_for(recommendation_id)}


def _anomalies_with_status(dataset=None):
    return anomaly_engine.with_status(detect_anomalies(dataset))


def _get_anomaly(anomaly_id: str):
    a = next((x for x in anomaly_engine.with_status(anomaly_history()) if x["id"] == anomaly_id), None)
    if not a:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return a


def _anomaly_detail(anomaly_id: str):
    a = _get_anomaly(anomaly_id)
    ds = get_dataset()
    return a | {
        "investigation": anomaly_engine.investigation(a, ds, _recs_with_status(ds)),
        "history": anomaly_events_for(anomaly_id),
    }


@app.get("/api/anomalies")
def get_anomalies():
    """Anomalies detected in the latest billing month, most severe first."""
    return _anomalies_with_status()


@app.get("/api/anomalies/history")
def get_anomaly_history():
    history = anomaly_engine.with_status(anomaly_history())
    return {"anomalies": history, "summary": anomaly_engine.summary(history)}


@app.get("/api/anomalies/config")
def get_anomaly_config():
    return {"version": anomaly_engine.DETECTOR_VERSION, "thresholds": anomaly_engine.CONFIG,
            "types": anomaly_engine.TYPE_LABELS, "statuses": anomaly_engine.STATUSES,
            "resolutions": anomaly_engine.RESOLUTIONS,
            "note": "Example thresholds. They are not yet user-configurable."}


@app.get("/api/anomalies/{anomaly_id}")
def get_anomaly(anomaly_id: str):
    return _anomaly_detail(anomaly_id)


@app.post("/api/anomalies/{anomaly_id}/actions")
def anomaly_action(anomaly_id: str, payload: AnomalyActionIn):
    a = _get_anomaly(anomaly_id)
    try:
        anomaly_engine.apply_action(a, payload.action, payload.resolution, payload.note)
    except anomaly_engine.TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _anomaly_detail(anomaly_id)


@app.post("/api/recommendations/{recommendation_id}/feedback")
def feedback(recommendation_id: str, payload: FeedbackIn):
    """v1 endpoint, kept for compatibility. Maps onto the lifecycle actions."""
    rec = _get_rec(recommendation_id)
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
def copilot(payload: ChatIn):
    ds = get_dataset()
    return copilot_engine.answer(
        payload.question.strip(), dashboard(), _recs_with_status(ds), _anomalies_with_status(ds), ds["dataset_id"]
    )


@app.get("/")
def root():
    return {"message": "CloudPilot AI API. Visit /docs for API documentation."}
