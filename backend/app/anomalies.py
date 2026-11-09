"""Cost anomaly detection v2.

Deterministic, explainable detection on monthly service spend.

Methods (simple, robust baselines first; ML only once these are measured):
  * Baseline      median of up to 6 prior months (robust to one-off spikes)
  * Spread        1.4826 × median absolute deviation, floored at 5% of baseline
  * Robust z      (current − baseline) / spread
  * Month-over-month change, shown as context

Anomaly types:
  * spike          deviation ≥ 20% above baseline AND robust z ≥ 3
  * gradual_growth 3 consecutive month-over-month increases, each < 20%,
                   cumulative ≥ 15% (classified instead of a spike when MoM < 20%)
  * new_service    spend in the current month with no spend in the baseline

An anomaly means *unusual* spend, not necessarily waste or a known cause.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Optional

from . import db

DETECTOR_VERSION = "2.0.0"

# Example thresholds; exposed via /api/anomalies/config and meant to become user-configurable.
CONFIG = {
    "baseline_months": 6,
    "min_baseline_months": 3,
    "spike_min_deviation_percent": 20.0,
    "spike_min_robust_z": 3.0,
    "spread_floor_percent": 5.0,
    "gradual_months": 3,
    "gradual_max_step_percent": 20.0,
    "gradual_min_cumulative_percent": 15.0,
    "severity": {"critical": 60.0, "high": 30.0, "medium": 20.0},
}

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

TYPE_LABELS = {
    "spike": "Sudden spending spike",
    "gradual_growth": "Gradual spending growth",
    "new_service": "New service spend",
}

INVESTIGATION_AREAS = {
    "EC2": ["Increase in running instance hours", "Newly launched instances", "Instance type changes",
            "Expired Reserved Instance or Savings Plan coverage", "Increased workload demand"],
    "RDS": ["Instance class changes", "New read replicas or Multi-AZ enabled", "Storage or IOPS growth",
            "Backup retention changes"],
    "S3": ["Storage growth", "Request volume increase", "Data transfer out", "Replication changes"],
    "EBS": ["New volumes or snapshots", "Volume type or provisioned IOPS changes", "Snapshot retention"],
    "CloudWatch": ["Log ingestion volume (verbose or debug logging)", "New custom metrics", "Log retention periods",
                   "Dashboard and alarm count"],
    "Lambda": ["Invocation volume", "Function duration or memory changes", "Provisioned concurrency"],
}

# ----------------------------------------------------------- lifecycle ---

STATUSES = ["open", "acknowledged", "investigating", "resolved"]

TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "acknowledge": ({"open"}, "acknowledged"),
    "investigate": ({"open", "acknowledged"}, "investigating"),
    "resolve": ({"open", "acknowledged", "investigating"}, "resolved"),
    "reopen": ({"acknowledged", "investigating", "resolved"}, "open"),
}

RESOLUTIONS = {
    "expected_change": "Expected change (planned growth or launch)",
    "fixed": "Root cause found and fixed",
    "false_positive": "False positive",
    "other": "Other",
}


class TransitionError(ValueError):
    pass


# ----------------------------------------------------------- detection ---

def _pct(a: float, b: float) -> Optional[float]:
    return round((a - b) / b * 100, 1) if b else None


def _severity(kind: str, deviation: float) -> str:
    if kind == "gradual_growth":
        return "Low"
    if kind == "new_service":
        return "Medium"
    s = CONFIG["severity"]
    return "Critical" if deviation >= s["critical"] else "High" if deviation >= s["high"] else "Medium"


def _detected_at(month: str, latest: str, generated_at: str) -> str:
    """Synthetic detection time: the snapshot time for the current month, else the day after month end."""
    if month == latest:
        return generated_at
    y, m = map(int, month.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return datetime(nxt.year, nxt.month, nxt.day, 6, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")


def detect_for_month(series: dict[str, dict[str, float]], months: list[str], idx: int,
                     latest: str, generated_at: str, dataset_id: str) -> list[dict]:
    """Detect anomalies for months[idx] using only data available up to that month."""
    month = months[idx]
    prior_months = months[max(0, idx - CONFIG["baseline_months"]):idx]
    out = []
    for service, costs in series.items():
        current = costs.get(month)
        if current is None:
            continue
        prior = [costs[m] for m in prior_months if costs.get(m) is not None]
        previous = costs.get(months[idx - 1]) if idx > 0 else None
        base = {
            "service": service, "month": month, "current_cost": round(current, 2),
            "previous_month": months[idx - 1] if idx > 0 else None,
            "previous_cost": round(previous, 2) if previous is not None else None,
            "mom_percent": _pct(current, previous) if previous else None,
            "dataset_id": dataset_id, "detector_version": DETECTOR_VERSION,
            "detected_at": _detected_at(month, latest, generated_at),
        }

        if not prior or all(p == 0 for p in prior):
            if idx > 0 and current > 0:
                out.append(base | _finish("new_service", base, prior_months, 0.0, None, None))
            continue
        if len(prior) < CONFIG["min_baseline_months"]:
            continue

        baseline = median(prior)
        mad = median(abs(p - baseline) for p in prior)
        spread = max(1.4826 * mad, baseline * CONFIG["spread_floor_percent"] / 100)
        z = round((current - baseline) / spread, 2) if spread else None
        deviation = _pct(current, baseline) or 0.0

        # Gradual growth: N consecutive modest increases ending this month.
        n = CONFIG["gradual_months"]
        window = [costs.get(m) for m in months[max(0, idx - n):idx + 1]]
        steps = [_pct(b, a) for a, b in zip(window, window[1:]) if a and b]
        gradual = (
            len(steps) == n
            and all(0 < s < CONFIG["gradual_max_step_percent"] for s in steps)
            and (_pct(window[-1], window[0]) or 0) >= CONFIG["gradual_min_cumulative_percent"]
        )
        mom = base["mom_percent"] or 0
        if gradual and mom < CONFIG["gradual_max_step_percent"]:
            out.append(base | _finish("gradual_growth", base, prior_months, baseline, spread, z,
                                      deviation, steps, _pct(window[-1], window[0])))
        elif deviation >= CONFIG["spike_min_deviation_percent"] and z is not None and z >= CONFIG["spike_min_robust_z"]:
            out.append(base | _finish("spike", base, prior_months, baseline, spread, z, deviation))
    return out


def _finish(kind, base, prior_months, baseline, spread, z, deviation=0.0, steps=None, cumulative=None) -> dict:
    service, month = base["service"], base["month"]
    severity = _severity(kind, deviation)
    if kind == "spike":
        summary = (f"{service} spend is {deviation:.1f}% above its {len(prior_months)}-month median baseline "
                   f"(robust z-score {z}).")
    elif kind == "gradual_growth":
        summary = (f"{service} spend grew {len(steps)} months in a row "
                   f"({', '.join(f'+{s}%' for s in steps)}), {cumulative}% cumulatively.")
    else:
        summary = f"{service} has spend this month but none in the baseline period."
    return {
        "id": f"anom-{service.lower()}-{month}-{kind}",
        "type": kind,
        "type_label": TYPE_LABELS[kind],
        "severity": severity,
        "baseline": {
            "method": "Median of prior months" if kind != "new_service" else "No prior spend",
            "value": round(baseline, 2),
            "spread": round(spread, 2) if spread else None,
            "observation_window": {"start": prior_months[0] if prior_months else None,
                                   "end": prior_months[-1] if prior_months else None,
                                   "months": len(prior_months)},
        },
        "deviation": {
            "absolute": round(base["current_cost"] - baseline, 2),
            "percent": deviation,
            "robust_z": z,
            "steps_percent": steps,
            "cumulative_percent": cumulative,
        },
        "summary": summary,
        "explanation": (summary + " This identifies unusual spend to investigate; it does not establish a root cause "
                        "or prove waste."),
        # v1-compatible fields used by older clients and the copilot
        "current_month": month,
        "change_percent": base["mom_percent"] if base["mom_percent"] is not None else deviation,
    }


def detect_all(dataset: dict) -> list[dict]:
    """Walk-forward detection across every month: current and historical anomalies."""
    series: dict[str, dict[str, float]] = {}
    for row in dataset["spend"]:
        series.setdefault(row["service"], {})[row["month"]] = row["cost"]
    months = sorted({row["month"] for row in dataset["spend"]})
    latest = months[-1]
    out = []
    for idx in range(1, len(months)):
        out += detect_for_month(series, months, idx, latest, dataset["generated_at"], dataset["dataset_id"])
    for a in out:
        a["is_current"] = a["month"] == latest
    return sorted(out, key=lambda a: (a["month"], -SEVERITY_ORDER[a["severity"]], a["deviation"]["percent"]),
                  reverse=True)


def current(dataset: dict) -> list[dict]:
    """Anomalies detected in the latest billing month, most severe first."""
    cur = [a for a in detect_all(dataset) if a["is_current"]]
    return sorted(cur, key=lambda a: (SEVERITY_ORDER[a["severity"]], -a["deviation"]["percent"]))


# ------------------------------------------------------ investigation ---

def investigation(anomaly: dict, dataset: dict, recommendations: list[dict]) -> dict:
    service = anomaly["service"]
    months = sorted({r["month"] for r in dataset["spend"]})
    timeline = [{"month": r["month"], "cost": r["cost"]} for r in dataset["spend"] if r["service"] == service]
    timeline.sort(key=lambda r: r["month"])
    resources = [r for r in dataset["resources"] if r["service"] == service]
    attributed = round(sum(r["monthly_cost"] for r in resources), 2)
    total = anomaly["current_cost"]
    return {
        "timeline": timeline,
        "anomaly_month": anomaly["month"],
        "baseline_value": anomaly["baseline"]["value"],
        "attribution": {
            "resources": [
                {"id": r["id"], "type": r["type"], "region": r["region"], "environment": r.get("environment"),
                 "monthly_cost": r["monthly_cost"]}
                for r in sorted(resources, key=lambda r: r["monthly_cost"], reverse=True)
            ],
            "attributed_cost": attributed,
            "unattributed_cost": round(max(total - attributed, 0), 2),
            "coverage_percent": round(attributed / total * 100, 1) if total else None,
            "note": ("Only resources in the synthetic inventory are listed. Resource-level billing history is not in "
                     "this dataset, so the remaining spend cannot be attributed to specific resources yet."),
        },
        "investigation_areas": INVESTIGATION_AREAS.get(service, ["Usage changes", "Pricing changes", "New deployments"]),
        "related_recommendations": [
            {"id": r["id"], "resource_id": r["resource_id"], "title": r["title"],
             "monthly_savings": r["savings"]["monthly"], "status": r.get("status", "open")}
            for r in recommendations if r["service"] == service
        ],
        "next_step": "Break down the service's cost by resource, usage type and region for the anomaly month.",
        "months_in_dataset": len(months),
    }


# ---------------------------------------------------------- lifecycle ---

def effective_state(event: Optional[dict]) -> dict:
    if not event:
        return {"status": "open", "updated_at": None, "resolution": None, "resolution_label": None, "note": None}
    return {
        "status": event["to_status"],
        "updated_at": event["created_at"],
        "resolution": event.get("reason"),
        "resolution_label": RESOLUTIONS.get(event.get("reason") or ""),
        "note": event.get("note"),
    }


def with_status(anomalies: list[dict]) -> list[dict]:
    latest = db.latest_anomaly_events()
    for a in anomalies:
        a["lifecycle"] = effective_state(latest.get(a["id"]))
        a["status"] = a["lifecycle"]["status"]
    return anomalies


def apply_action(anomaly: dict, action: str, resolution: Optional[str] = None, note: Optional[str] = None) -> dict:
    if action not in TRANSITIONS:
        raise TransitionError(f"Unknown action '{action}'")
    allowed, to_status = TRANSITIONS[action]
    cur = effective_state(db.latest_anomaly_events().get(anomaly["id"]))["status"]
    if cur not in allowed:
        raise TransitionError(f"Cannot '{action}' an anomaly that is '{cur}'")
    if action == "resolve" and resolution not in RESOLUTIONS:
        raise TransitionError("A resolution is required")
    if action == "resolve" and resolution == "other" and not (note or "").strip():
        raise TransitionError("Please describe the resolution when choosing 'Other'")
    return db.record_anomaly_event(
        anomaly_id=anomaly["id"], action=action, from_status=cur, to_status=to_status,
        reason=resolution if action == "resolve" else None, note=(note or "").strip() or None,
        detector_version=DETECTOR_VERSION, dataset_id=anomaly["dataset_id"],
    )


def summary(anomalies: list[dict]) -> dict:
    by_service: dict[str, int] = {}
    for a in anomalies:
        by_service[a["service"]] = by_service.get(a["service"], 0) + 1
    by_status = {s: sum(1 for a in anomalies if a["status"] == s) for s in STATUSES}
    return {
        "total": len(anomalies),
        "current": sum(1 for a in anomalies if a["is_current"]),
        "unresolved": len(anomalies) - by_status["resolved"],
        "by_status": by_status,
        "by_service": dict(sorted(by_service.items(), key=lambda x: -x[1])),
        "by_severity": {s: sum(1 for a in anomalies if a["severity"] == s) for s in SEVERITY_ORDER},
    }
