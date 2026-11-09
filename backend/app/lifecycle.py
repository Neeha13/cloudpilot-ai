"""Recommendation lifecycle: statuses, allowed transitions and analytics.

Generated → reviewed → approved → executed → verified are separate events.
"implemented" here means the user *reported* the change; savings remain an
estimate until verified against post-change billing data (not yet built).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from . import db
from .recommendations import RULESET_VERSION

STATUSES = ["open", "investigating", "planned", "implemented", "snoozed", "dismissed"]

# action -> (allowed from-statuses, resulting status)
TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "investigate": ({"open"}, "investigating"),
    "plan": ({"open", "investigating"}, "planned"),
    "implement": ({"investigating", "planned"}, "implemented"),
    "snooze": ({"open", "investigating"}, "snoozed"),
    "dismiss": ({"open", "investigating", "planned"}, "dismissed"),
    "reopen": ({"investigating", "planned", "implemented", "snoozed", "dismissed"}, "open"),
}

DISMISS_REASONS = {
    "business_critical": "Resource is business-critical",
    "incorrect": "Recommendation is incorrect",
    "already_optimized": "Already optimized",
    "insufficient_information": "Not enough information",
    "not_feasible": "Action not feasible",
    "other": "Other",
}

IN_PROGRESS = {"investigating", "planned"}
ACCEPTED = {"investigating", "planned", "implemented"}


class TransitionError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def effective_state(event: Optional[dict]) -> dict:
    """Current lifecycle state derived from the latest event (snoozes expire automatically)."""
    if not event:
        return {"status": "open", "updated_at": None, "reason": None, "note": None, "snooze_until": None}
    status = event["to_status"]
    if status == "snoozed" and event.get("snooze_until"):
        if datetime.fromisoformat(event["snooze_until"].replace("Z", "+00:00")) <= _now():
            status = "open"
    return {
        "status": status,
        "updated_at": event["created_at"],
        "reason": event.get("reason"),
        "reason_label": DISMISS_REASONS.get(event.get("reason") or ""),
        "note": event.get("note"),
        "snooze_until": event.get("snooze_until") if status == "snoozed" else None,
    }


def with_status(recs: list[dict]) -> list[dict]:
    latest = db.latest_events()
    for r in recs:
        r["lifecycle"] = effective_state(latest.get(r["id"]))
        r["status"] = r["lifecycle"]["status"]
    return recs


def apply_action(rec: dict, action: str, reason: Optional[str] = None,
                 note: Optional[str] = None, snooze_days: Optional[int] = None) -> dict:
    if action not in TRANSITIONS:
        raise TransitionError(f"Unknown action '{action}'")
    allowed_from, to_status = TRANSITIONS[action]
    current = effective_state(db.latest_events().get(rec["id"]))["status"]
    if current not in allowed_from:
        raise TransitionError(f"Cannot '{action}' a recommendation that is '{current}'")
    if action == "dismiss" and reason not in DISMISS_REASONS:
        raise TransitionError("A dismissal reason is required")
    if action == "dismiss" and reason == "other" and not (note or "").strip():
        raise TransitionError("Please describe the reason when choosing 'Other'")
    snooze_until = None
    if action == "snooze":
        snooze_until = (_now() + timedelta(days=snooze_days or 7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return db.record_event(
        recommendation_id=rec["id"], action=action, from_status=current, to_status=to_status,
        reason=reason if action == "dismiss" else None, note=(note or "").strip() or None,
        snooze_until=snooze_until, ruleset_version=RULESET_VERSION,
        dataset_id=rec.get("dataset_id"), estimated_monthly_savings=rec["savings"]["monthly"],
        snapshot_id=rec.get("snapshot_id"),
    )


def analytics(recs: list[dict]) -> dict:
    """Decision analytics computed from actual recorded interactions only."""
    by_status = {s: 0 for s in STATUSES}
    savings = {s: 0.0 for s in STATUSES}
    for r in recs:
        by_status[r["status"]] += 1
        savings[r["status"]] += r["savings"]["monthly"]
    decided = len(recs) - by_status["open"]
    accepted = sum(by_status[s] for s in ACCEPTED)
    acceptance_base = accepted + by_status["dismissed"]
    events = db.events_for()
    current_ids = {r["id"] for r in recs}
    reasons: dict[str, int] = {}
    for r in recs:
        if r["status"] == "dismissed" and r["lifecycle"].get("reason"):
            label = DISMISS_REASONS[r["lifecycle"]["reason"]]
            reasons[label] = reasons.get(label, 0) + 1
    return {
        "total_recommendations": len(recs),
        "by_status": by_status,
        "decision_coverage": {"decided": decided, "total": len(recs),
                              "rate": round(decided / len(recs), 3) if recs else None},
        "acceptance_rate": round(accepted / acceptance_base, 3) if acceptance_base else None,
        "dismissal_reasons": reasons,
        "savings_monthly": {
            "potential_total": round(sum(r["savings"]["monthly"] for r in recs), 2),
            "open": round(savings["open"], 2),
            "in_progress": round(sum(savings[s] for s in IN_PROGRESS), 2),
            "implemented_unverified": round(savings["implemented"], 2),
            "dismissed": round(savings["dismissed"], 2),
            "snoozed": round(savings["snoozed"], 2),
        },
        "events_recorded": len([e for e in events if e["recommendation_id"] in current_ids]),
        "notes": [
            "Implemented savings are estimates until verified against post-change billing data.",
            "Rates are computed from recorded decisions in this environment, not from user research.",
        ],
    }
