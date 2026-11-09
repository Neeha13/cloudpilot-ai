"""Recommendation Intelligence v2.

Deterministic, evidence-backed recommendations. Every number shown to a user
(savings, confidence, risk, priority) is computed here from the shared dataset
snapshot. The copilot / LLM layer may only *explain* these results; it never
produces figures of its own.

Priority model (a product hypothesis to validate, not an industry standard):

    Priority = 0.35·S + 0.25·C + 0.20·B + 0.10·E + 0.10·R

Each factor is normalised to 0–100:
    S  savings potential      log-scaled monthly estimate, $500/mo or more = 100
    C  confidence             mean of evidence completeness, freshness,
                              observation window and signal strength
    B  business impact        40 base, +35 if the service has an active cost
                              anomaly, up to +25 by share of the service's spend
    E  ease of implementation rule-specific effort estimate
    R  risk safety            higher = safer; rule base, lowered for production
                              and missing safeguards
"""
from __future__ import annotations

import math
from typing import Callable, Optional

RULESET_VERSION = "2.0.0"

WEIGHTS = {"savings": 0.35, "confidence": 0.25, "business_impact": 0.20, "ease": 0.10, "risk_safety": 0.10}

FACTOR_DEFINITIONS = {
    "savings": "Savings potential: estimated monthly saving, log-scaled so that $500/month or more scores 100.",
    "confidence": "Confidence: average of evidence completeness, data freshness, observation window and signal strength. Capped below High when any required evidence is missing.",
    "business_impact": "Business impact: 40 base, +35 when the service has an active cost anomaly, up to +25 by the saving's share of that service's monthly spend.",
    "ease": "Ease: how quickly and simply the change can be made (rule-specific estimate).",
    "risk_safety": "Risk safety: higher means safer. Starts from a rule baseline and is lowered for production workloads and missing safeguards.",
}

SAVINGS_CAP = 500.0
MISSING_EVIDENCE_CAP = 75  # confidence score at which "High" begins
PRODUCTION_RISK_PENALTY = 15


# ---------------------------------------------------------------- helpers ---

def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def _level(score: float, high: float, medium: float) -> str:
    return "High" if score >= high else "Medium" if score >= medium else "Low"


def confidence_level(score: float) -> str:
    return _level(score, 75, 50)


def priority_level(score: float) -> str:
    return _level(score, 65, 50)


def risk_level(safety: float) -> str:
    # Inverted: a high safety score means low operational risk.
    return "Low" if safety >= 70 else "Medium" if safety >= 40 else "High"


def effort_level(ease: float) -> str:
    return "Low" if ease >= 70 else "Moderate" if ease >= 45 else "High"


def savings_score(monthly: float) -> float:
    return _clamp(100 * math.log10(1 + monthly) / math.log10(1 + SAVINGS_CAP))


def _freshness_score(days: int) -> tuple[float, str]:
    if days <= 1:
        return 100, f"Metrics updated {days} day ago" if days == 1 else "Metrics updated today"
    if days <= 3:
        return 85, f"Metrics updated {days} days ago"
    if days <= 7:
        return 65, f"Metrics updated {days} days ago"
    return 40, f"Metrics are {days} days old"


def _window_score(days: int, target: int) -> tuple[float, str]:
    if days >= target:
        return 100, f"{days} days observed (target {target}+)"
    if days >= target / 2:
        return 70, f"Only {days} days observed (target {target}+)"
    return 40, f"Only {days} days observed (target {target}+)"


def _completeness(metrics: dict, required: list[str]) -> tuple[float, str, list[str]]:
    missing = [m for m in required if metrics.get(m) is None]
    present = len(required) - len(missing)
    score = 100 * present / len(required) if required else 100
    note = f"{present} of {len(required)} required metrics available"
    if missing:
        note += f"; missing: {', '.join(_METRIC_LABELS.get(m, m) for m in missing)}"
    return score, note, missing


_METRIC_LABELS = {
    "avg_cpu": "average CPU",
    "p95_cpu": "p95 CPU",
    "memory_utilization": "memory utilization",
    "avg_connections": "average connections",
    "infrequent_access_share": "access-frequency profile",
    "access_logging": "access logs",
}


def _fmt_pct(v: Optional[float]) -> str:
    return "Not collected" if v is None else f"{v:g}%"


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _ev(label: str, value: str, source: str = "Resource inventory") -> dict:
    return {"label": label, "value": value, "source": source}


# ------------------------------------------------------------------ rules ---
# A rule returns None when it does not apply, or a dict with the rule-specific
# parts of a recommendation. Scoring and assembly are shared below.

def _rule_ec2_low_utilization(r: dict) -> Optional[dict]:
    if r["service"] != "EC2" or r["status"] != "running":
        return None
    m = r["metrics"]
    if m.get("avg_cpu") is None or m["avg_cpu"] >= 10:
        return None
    p95 = m.get("p95_cpu")
    rate = 0.35
    monthly = round(r["monthly_cost"] * rate, 2)
    signal = 100 if (p95 is not None and p95 < 20) else 70 if (p95 is not None and p95 < 40) else 35
    signal_note = (
        f"Average CPU {m['avg_cpu']}% with p95 {_fmt_pct(p95)}: "
        + ("consistently idle" if signal == 100 else "mostly idle with moderate peaks" if signal == 70
           else "bursty workload: peaks may need current capacity")
    )
    return {
        "rule_id": "ec2-low-utilization",
        "category": "Compute",
        "title": "Investigate low-utilization compute instance",
        "summary": f"Average CPU is {m['avg_cpu']}% over {r['observation_days']} days on a {r['type']} instance.",
        "detected": f"Average CPU below the 10% threshold ({m['avg_cpu']}%) for a running instance.",
        "why_it_matters": "Instances billed for capacity they do not use are one of the most common sources of compute waste.",
        "suggested_action": "Review workload patterns and peak utilization, then test one instance size smaller or a scheduled shutdown outside working hours.",
        "evidence": [
            _ev("Average CPU", _fmt_pct(m["avg_cpu"]), "CloudWatch metrics (synthetic)"),
            _ev("p95 CPU", _fmt_pct(p95), "CloudWatch metrics (synthetic)"),
            _ev("Memory utilization", _fmt_pct(m.get("memory_utilization")), "CloudWatch agent (synthetic)"),
            _ev("Instance type", r["type"]),
            _ev("Running hours this month", str(r.get("running_hours", "Unknown"))),
            _ev("Monthly cost", _money(r["monthly_cost"]), "Billing data (synthetic)"),
        ],
        "required_metrics": ["avg_cpu", "p95_cpu", "memory_utilization"],
        "target_window": 30,
        "signal": (signal, signal_note),
        "savings": {
            "rate": rate,
            "method": "Illustrative reduction from moving one size down or scheduling off-hours shutdown.",
            "assumptions": [
                "35% reduction is a planning assumption, not a pricing quote.",
                "Assumes on-demand pricing with no Reserved Instance or Savings Plan coverage.",
                "Memory, network and peak CPU must fit the smaller size.",
            ],
        },
        "ease": 55,
        "ease_note": "Requires a resize or schedule change and a short validation window.",
        "risk_base": 65,
        "risks": [
            "A smaller instance may throttle under peak load.",
            "Memory pressure is unknown if memory metrics are not collected.",
            "Resizing requires a stop/start, causing brief downtime.",
        ],
        "verify": [
            "Check p95 and maximum CPU over at least 30 days, including month-end peaks.",
            "Install or check the CloudWatch agent for memory utilization.",
            "Confirm the owning team and any scheduled batch jobs.",
            "Confirm the instance is not covered by a Reserved Instance or Savings Plan.",
        ],
    }


def _rule_ebs_unattached(r: dict) -> Optional[dict]:
    if r["service"] != "EBS" or r.get("attached") is not False:
        return None
    rate = 1.0
    days = r.get("days_unattached", 0)
    signal = 95 if days >= 30 else 70 if days >= 7 else 45
    return {
        "rule_id": "ebs-unattached",
        "category": "Storage",
        "title": "Review unattached storage volume",
        "summary": f"Volume has been unattached for {days} days and still incurs storage charges.",
        "detected": "Volume status is 'available' and it is not attached to any instance.",
        "why_it_matters": "Unattached volumes are billed in full while providing no value to a running workload.",
        "suggested_action": "Confirm no backup, recovery or migration dependency. If not needed, take a snapshot and delete the volume through your change process.",
        "evidence": [
            _ev("Volume status", r["status"]),
            _ev("Attached", "No"),
            _ev("Days unattached", str(days)),
            _ev("Recent snapshot", "Yes" if r.get("recent_snapshot") else "No"),
            _ev("Size", f"{r.get('size_gb', '?')} GB"),
            _ev("Monthly cost", _money(r["monthly_cost"]), "Billing data (synthetic)"),
        ],
        "required_metrics": [],
        "target_window": 30,
        "window_days": days,
        "signal": (signal, f"Unattached for {days} days"),
        "savings": {
            "rate": rate,
            "method": "The full volume cost stops if it is deleted. A retained snapshot would add a smaller cost.",
            "assumptions": [
                "Assumes the volume is not required for recovery, migration or audit.",
                "Snapshot storage cost (if one is kept) is not subtracted.",
            ],
        },
        "ease": 80,
        "ease_note": "Snapshot and delete are quick; the main work is confirming ownership.",
        "risk_base": 85,
        "risk_adjustments": [] if r.get("recent_snapshot") else [(-10, "No recent snapshot exists")],
        "risks": [
            "Deleting a volume is irreversible without a snapshot.",
            "The volume may hold data for a stopped instance or a pending migration.",
        ],
        "verify": [
            "Identify the owner (the volume is not tagged with an owning team)." if not r.get("owner_team")
            else f"Confirm with the owning team ({r['owner_team']}).",
            "Check whether any stopped instance or launch template references this volume.",
            "Take a snapshot before deletion.",
        ],
    }


def _rule_rds_overprovisioned(r: dict) -> Optional[dict]:
    if r["service"] != "RDS":
        return None
    m = r["metrics"]
    if m.get("avg_cpu") is None or m["avg_cpu"] >= 20:
        return None
    rate = 0.25
    checks = [
        (m.get("p95_cpu") is not None and m["p95_cpu"] < 40, "p95 CPU < 40%"),
        (m.get("memory_utilization") is not None and m["memory_utilization"] < 50, "memory < 50%"),
        (m.get("avg_connections") is not None and m["avg_connections"] < 20, "connections < 20"),
    ]
    passed = sum(1 for ok, _ in checks if ok)
    signal = 40 + 20 * passed
    return {
        "rule_id": "rds-overprovisioned",
        "category": "Database",
        "title": "Review database capacity",
        "summary": f"Average CPU is {m['avg_cpu']}% on a {r['type']} {'Multi-AZ ' if r.get('multi_az') else ''}instance.",
        "detected": f"Average CPU below the 20% threshold ({m['avg_cpu']}%).",
        "why_it_matters": "Database instances are among the most expensive resources per unit, so over-provisioning is costly.",
        "suggested_action": "Review CPU, memory, I/O, connections and peak periods, then test a smaller instance class in a non-production copy first.",
        "evidence": [
            _ev("Average CPU", _fmt_pct(m["avg_cpu"]), "CloudWatch metrics (synthetic)"),
            _ev("p95 CPU", _fmt_pct(m.get("p95_cpu")), "CloudWatch metrics (synthetic)"),
            _ev("Memory utilization", _fmt_pct(m.get("memory_utilization")), "CloudWatch metrics (synthetic)"),
            _ev("Average connections", str(m.get("avg_connections", "Not collected"))),
            _ev("Instance class", r["type"] + (" (Multi-AZ)" if r.get("multi_az") else "")),
            _ev("Monthly cost", _money(r["monthly_cost"]), "Billing data (synthetic)"),
        ],
        "required_metrics": ["avg_cpu", "p95_cpu", "memory_utilization", "avg_connections"],
        "target_window": 30,
        "signal": (signal, f"{passed} of 3 secondary indicators also low ({', '.join(l for ok, l in checks if ok) or 'none'})"),
        "savings": {
            "rate": rate,
            "method": "Illustrative reduction from moving to the next smaller instance class.",
            "assumptions": [
                "25% reduction is a planning assumption, not a pricing quote.",
                "Storage and I/O charges are unchanged.",
                "Assumes no Reserved Instance coverage on this class.",
            ],
        },
        "ease": 30,
        "ease_note": "Needs a maintenance window, a performance test and a rollback plan.",
        "risk_base": 50,
        "risks": [
            "Smaller classes reduce memory and buffer cache, which can raise query latency.",
            "A class change triggers a failover or restart.",
            "Peak periods (month-end, batch jobs) may not appear in averages.",
        ],
        "verify": [
            "Review p95/max CPU, memory, IOPS and connections over 30+ days.",
            "Check slow-query logs and buffer cache hit ratio.",
            "Agree a maintenance window and rollback plan with the owning team.",
        ],
    }


def _rule_s3_lifecycle(r: dict) -> Optional[dict]:
    if r["service"] != "S3" or r.get("lifecycle_policy", True):
        return None
    m = r["metrics"]
    rate = 0.12
    share = m.get("infrequent_access_share")
    signal = 70 if (share is not None and share >= 0.5) else 45
    return {
        "rule_id": "s3-no-lifecycle",
        "category": "Storage",
        "title": "Review storage lifecycle policy",
        "summary": f"No lifecycle policy on a {r.get('size_gb', '?')} GB bucket; ~{int((share or 0) * 100)}% of objects look infrequently accessed.",
        "detected": "The bucket has no lifecycle rules recorded.",
        "why_it_matters": "Without lifecycle rules, rarely-read objects stay in the most expensive storage class indefinitely.",
        "suggested_action": "Review access patterns and retention requirements, then add lifecycle transitions for eligible objects.",
        "evidence": [
            _ev("Lifecycle policy", "None"),
            _ev("Bucket size", f"{r.get('size_gb', '?')} GB"),
            _ev("Infrequently accessed share", "Not collected" if share is None else f"{int(share * 100)}%", "Storage analytics (synthetic)"),
            _ev("Access logging", "Enabled" if m.get("access_logging") else "Disabled"),
            _ev("Monthly cost", _money(r["monthly_cost"]), "Billing data (synthetic)"),
        ],
        "required_metrics": ["infrequent_access_share", "access_logging"],
        "required_truthy": True,
        "target_window": 90,
        "signal": (signal, "Majority of objects infrequently accessed" if signal == 70 else "Access profile unclear"),
        "savings": {
            "rate": rate,
            "method": "Illustrative blended reduction from transitioning eligible objects to an infrequent-access class.",
            "assumptions": [
                "12% blended reduction is a planning assumption.",
                "Retrieval fees and minimum storage durations may offset savings.",
                "Compliance retention rules may prevent transitions.",
            ],
        },
        "ease": 70,
        "ease_note": "A lifecycle rule is a configuration change, but access patterns must be confirmed first.",
        "risk_base": 60,
        "risks": [
            "Frequently-read objects moved to infrequent access incur retrieval charges.",
            "Archive tiers add retrieval latency.",
        ],
        "verify": [
            "Enable access logging or storage analytics to confirm access patterns.",
            "Check data-retention and compliance requirements.",
            "Start with a prefix-scoped rule before applying it bucket-wide.",
        ],
    }


RULES: list[Callable[[dict], Optional[dict]]] = [
    _rule_ec2_low_utilization,
    _rule_ebs_unattached,
    _rule_rds_overprovisioned,
    _rule_s3_lifecycle,
]


# --------------------------------------------------------------- assembly ---

def _confidence(r: dict, spec: dict) -> dict:
    metrics = r.get("metrics", {})
    required = spec["required_metrics"]
    if spec.get("required_truthy"):
        # access_logging=False means "logs not available", i.e. missing evidence.
        metrics = {k: (v if v else None) for k, v in metrics.items()}
    comp, comp_note, missing = _completeness(metrics, required)
    fresh, fresh_note = _freshness_score(r.get("metrics_age_days", 30))
    window_days = spec.get("window_days", r.get("observation_days", 0))
    win, win_note = _window_score(window_days, spec["target_window"])
    sig, sig_note = spec["signal"]
    factors = [
        {"name": "Evidence completeness", "score": round(comp), "note": comp_note},
        {"name": "Data freshness", "score": round(fresh), "note": fresh_note},
        {"name": "Observation window", "score": round(win), "note": win_note},
        {"name": "Signal strength", "score": round(sig), "note": sig_note},
    ]
    score = round(sum(f["score"] for f in factors) / len(factors))
    capped = False
    if missing and score >= MISSING_EVIDENCE_CAP:
        # Guardrail: a recommendation with missing required evidence can never be "High" confidence.
        score, capped = MISSING_EVIDENCE_CAP - 1, True
    return {"score": score, "level": confidence_level(score), "factors": factors,
            "missing_evidence": [_METRIC_LABELS.get(m, m) for m in missing], "capped_for_missing_evidence": capped}


def _risk(r: dict, spec: dict) -> dict:
    safety = spec["risk_base"]
    notes = []
    if r.get("environment") == "production":
        safety -= PRODUCTION_RISK_PENALTY
        notes.append("Production workload")
    for delta, note in spec.get("risk_adjustments", []):
        safety += delta
        notes.append(note)
    safety = _clamp(safety)
    level = risk_level(safety)
    explanation = {
        "Low": "Low risk: reversible or isolated change; workloads are unlikely to be affected.",
        "Medium": "Medium risk: could affect performance or availability if assumptions are wrong; validate first.",
        "High": "High risk: likely to affect a critical workload if wrong; needs testing, a maintenance window and a rollback plan.",
    }[level]
    return {"level": level, "safety_score": round(safety), "explanation": explanation, "drivers": notes, "items": spec["risks"]}


def _business_impact(r: dict, monthly: float, anomalous_services: set[str], service_costs: dict) -> dict:
    score = 40.0
    drivers = []
    if r["service"] in anomalous_services:
        score += 35
        drivers.append(f"{r['service']} has an active cost anomaly")
    svc_cost = service_costs.get(r["service"], 0)
    share = monthly / svc_cost if svc_cost else 0
    score += min(25.0, share * 250)
    drivers.append(f"Saving equals {share * 100:.1f}% of {r['service']} spend this month")
    score = _clamp(score)
    return {"score": round(score), "level": _level(score, 70, 50), "drivers": drivers}


def _build(r: dict, spec: dict, anomalous_services: set[str], service_costs: dict, dataset_id: str) -> dict:
    rate = spec["savings"]["rate"]
    monthly = round(r["monthly_cost"] * rate, 2)
    annual = round(monthly * 12, 2)

    confidence = _confidence(r, spec)
    risk = _risk(r, spec)
    impact = _business_impact(r, monthly, anomalous_services, service_costs)
    ease = spec["ease"]

    factors = {
        "savings": round(savings_score(monthly)),
        "confidence": confidence["score"],
        "business_impact": impact["score"],
        "ease": ease,
        "risk_safety": risk["safety_score"],
    }
    priority_score = round(sum(WEIGHTS[k] * v for k, v in factors.items()), 1)

    return {
        "id": f"rec-{r['id']}",
        "version": RULESET_VERSION,
        "rule_id": spec["rule_id"],
        "dataset_id": dataset_id,
        "resource_id": r["id"],
        "service": r["service"],
        "region": r["region"],
        "environment": r.get("environment"),
        "owner_team": r.get("owner_team"),
        "category": spec["category"],
        "title": spec["title"],
        "summary": spec["summary"],
        "detected": spec["detected"],
        "why_it_matters": spec["why_it_matters"],
        "suggested_action": spec["suggested_action"],
        "evidence": spec["evidence"],
        "verify_before_acting": spec["verify"],
        "savings": {
            "monthly": monthly,
            "annual": annual,
            "kind": "estimate",
            "method": spec["savings"]["method"],
            "formula": f"{_money(r['monthly_cost'])} monthly cost × {rate * 100:g}% = {_money(monthly)}/month",
            "inputs": {"monthly_cost": r["monthly_cost"], "reduction_rate": rate},
            "assumptions": spec["savings"]["assumptions"],
        },
        "confidence": confidence,
        "risk": risk,
        "effort": {"level": effort_level(ease), "ease_score": ease, "explanation": spec["ease_note"]},
        "business_impact": impact,
        "priority": {
            "score": priority_score,
            "level": priority_level(priority_score),
            "factors": factors,
            "weights": WEIGHTS,
        },
        # v1-compatible flat fields
        "reason": spec["summary"],
        "suggestion": spec["suggested_action"],
        "monthly_savings_estimate": monthly,
        "annual_savings_estimate": annual,
        "risk_level": risk["level"],
        "priority_level": priority_level(priority_score),
        "assumptions": " ".join(spec["savings"]["assumptions"]),
    }


def generate(dataset: dict, anomalous_services: set[str]) -> list[dict]:
    current = dataset["billing_period"]["current"]
    service_costs = {row["service"]: row["cost"] for row in dataset["spend"] if row["month"] == current}
    out = []
    for resource in dataset["resources"]:
        for rule in RULES:
            spec = rule(resource)
            if spec:
                out.append(_build(resource, spec, anomalous_services, service_costs, dataset["dataset_id"]))
    return sorted(out, key=lambda x: (x["priority"]["score"], x["savings"]["monthly"]), reverse=True)


def scoring_model() -> dict:
    return {
        "version": RULESET_VERSION,
        "formula": "Priority = 0.35·S + 0.25·C + 0.20·B + 0.10·E + 0.10·R",
        "weights": WEIGHTS,
        "definitions": FACTOR_DEFINITIONS,
        "levels": {
            "priority": "High ≥ 65, Medium ≥ 50, otherwise Low",
            "confidence": "High ≥ 75, Medium ≥ 50, otherwise Low",
            "risk": "Risk safety ≥ 70 is Low risk, ≥ 40 Medium, otherwise High",
        },
        "status": "Initial product hypothesis. Weights have not yet been validated with users.",
    }
