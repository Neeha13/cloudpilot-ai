"""Synthetic demo dataset: generation and validation.

This module only *builds* datasets. Persistence, activation and reads live in
``snapshots.py``: every API reads the single active snapshot stored in SQLite,
so figures can never disagree between screens or change silently on restart.

Identifiers:
- ``dataset_id``  content hash of the data. Identical data -> identical id.
- ``snapshot_id`` one persisted, activated version (assigned in snapshots.py).
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import date, datetime, timezone
import math

SEED = 17
GENERATOR_VERSION = "1.0.0"

SCENARIO = {
    "id": "ec2-cost-spike",
    "name": "EC2 cost spike with idle and over-provisioned resources",
    "description": (
        "Compute spend jumps in the latest month and CloudWatch log ingestion grows steadily, "
        "while several resources show low utilization, an unattached volume and a bucket "
        "without lifecycle rules."
    ),
}

SERVICES = ["EC2", "RDS", "S3", "EBS", "CloudWatch", "Lambda"]
BASE = {"EC2": 2450, "RDS": 1280, "S3": 640, "EBS": 510, "CloudWatch": 240, "Lambda": 180}
HISTORY_MONTHS = 7


def _month_start(ref: date, months_back: int) -> date:
    """First day of the month ``months_back`` months before ``ref`` (calendar-correct)."""
    index = ref.year * 12 + (ref.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def _build_spend(ref: date, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for months_back in range(HISTORY_MONTHS - 1, -1, -1):
        month = _month_start(ref, months_back).strftime("%Y-%m")
        for service in SERVICES:
            factor = 1 + rng.uniform(-0.12, 0.12)
            if months_back == 0 and service == "EC2":
                factor = 1.38  # scenario: visible compute spike in the latest month
            if service == "CloudWatch" and months_back <= 3:
                factor = 1 + 0.07 * (4 - months_back)  # scenario: steady log-ingestion growth
            rows.append({"month": month, "service": service, "cost": round(BASE[service] * factor, 2)})
    return rows


def _build_resources() -> list[dict]:
    """Resource inventory. ``None`` means the metric was not collected (and lowers confidence)."""
    return [
        {
            "id": "i-demo-01", "service": "EC2", "type": "t3.large", "region": "us-east-1",
            "environment": "staging", "owner_team": "payments", "status": "running",
            "monthly_cost": 182.40, "running_hours": 720, "age_days": 93,
            "metrics": {"avg_cpu": 4.2, "p95_cpu": 11.0, "memory_utilization": None},
            "observation_days": 30, "metrics_age_days": 1,
        },
        {
            "id": "i-demo-02", "service": "EC2", "type": "m5.large", "region": "us-east-1",
            "environment": "production", "owner_team": None, "status": "running",
            "monthly_cost": 138.00, "running_hours": 720, "age_days": 62,
            "metrics": {"avg_cpu": 8.1, "p95_cpu": 63.0, "memory_utilization": None},
            "observation_days": 14, "metrics_age_days": 2,
        },
        {
            "id": "i-demo-03", "service": "EC2", "type": "t3.medium", "region": "ap-south-1",
            "environment": "production", "owner_team": "search", "status": "running",
            "monthly_cost": 74.20, "running_hours": 720, "age_days": 120,
            "metrics": {"avg_cpu": 46.0, "p95_cpu": 81.0, "memory_utilization": 58.0},
            "observation_days": 30, "metrics_age_days": 1,
        },
        {
            "id": "vol-demo-01", "service": "EBS", "type": "gp3 volume", "region": "us-east-1",
            "environment": "dev", "owner_team": None, "status": "available",
            "monthly_cost": 42.00, "size_gb": 525, "age_days": 75,
            "attached": False, "days_unattached": 61, "recent_snapshot": False,
            "metrics": {}, "observation_days": 61, "metrics_age_days": 1,
        },
        {
            "id": "vol-demo-02", "service": "EBS", "type": "gp3 volume", "region": "ap-south-1",
            "environment": "production", "owner_team": "search", "status": "in-use",
            "monthly_cost": 28.00, "size_gb": 350, "age_days": 20,
            "attached": True, "days_unattached": 0, "recent_snapshot": True,
            "metrics": {}, "observation_days": 20, "metrics_age_days": 1,
        },
        {
            "id": "db-demo-01", "service": "RDS", "type": "db.m5.large", "region": "us-east-1",
            "environment": "production", "owner_team": "payments", "status": "available",
            "monthly_cost": 310.00, "age_days": 88, "multi_az": True,
            "metrics": {"avg_cpu": 12.0, "p95_cpu": 38.0, "memory_utilization": 41.0, "avg_connections": 6},
            "observation_days": 30, "metrics_age_days": 1,
        },
        {
            "id": "bucket-demo-01", "service": "S3", "type": "standard storage", "region": "us-east-1",
            "environment": "production", "owner_team": "analytics", "status": "active",
            "monthly_cost": 65.00, "age_days": 150, "lifecycle_policy": False, "size_gb": 2800,
            "metrics": {"infrequent_access_share": 0.6, "access_logging": False},
            "observation_days": 90, "metrics_age_days": 3,
        },
    ]


def content_hash(seed: int, spend: list[dict], resources: list[dict], scenario_id: str = SCENARIO["id"]) -> str:
    # Same payload as before Sprint 1, so the default dataset keeps its existing dataset_id.
    payload = {"seed": seed, "scenario": scenario_id, "spend": spend, "resources": resources}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:10]
    return f"ds-{digest}"


def build_dataset(reference_date: date | None = None, seed: int = SEED) -> dict:
    """Generate a complete dataset for the billing month containing ``reference_date``.

    Pure and deterministic: the same reference month and seed always produce the
    same data and therefore the same ``dataset_id``.
    """
    ref = reference_date or date.today()
    spend = _build_spend(ref, seed)
    resources = _build_resources()
    months = sorted({row["month"] for row in spend})
    return {
        "dataset_id": content_hash(seed, spend, resources),
        "seed": seed,
        "generator_version": GENERATOR_VERSION,
        "reference_date": ref.isoformat(),
        "scenario": SCENARIO,
        "data_source": "synthetic_demo",
        "data_source_label": "Synthetic demo data",
        "billing_period": {"start": months[0], "end": months[-1], "current": months[-1]},
        "spend": spend,
        "resources": resources,
    }


class DatasetValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_dataset(ds: dict) -> list[str]:
    """Integrity rules a dataset must pass before it can become a snapshot."""
    errors: list[str] = []
    spend, resources = ds.get("spend") or [], ds.get("resources") or []
    if not spend:
        return ["dataset has no billing records"]
    months = sorted({r.get("month") for r in spend})
    try:
        ref = date.fromisoformat(ds["reference_date"])
        expected = [_month_start(ref, b).strftime("%Y-%m") for b in range(HISTORY_MONTHS - 1, -1, -1)]
        if months != expected:
            errors.append(f"billing months {months} are not the {HISTORY_MONTHS} consecutive months ending {expected[-1]}")
    except (KeyError, TypeError, ValueError):
        errors.append("reference_date is missing or invalid")
    seen = set()
    for r in spend:
        key = (r.get("month"), r.get("service"))
        if key in seen:
            errors.append(f"duplicate billing record {key}")
        seen.add(key)
        cost = r.get("cost")
        if r.get("service") not in SERVICES:
            errors.append(f"unknown service {r.get('service')!r}")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not math.isfinite(cost) or cost < 0:
            errors.append(f"invalid cost {cost!r} for {key}")
    for m in months:
        missing = set(SERVICES) - {r["service"] for r in spend if r.get("month") == m}
        if missing:
            errors.append(f"{m} is missing services {sorted(missing)}")
    bp = ds.get("billing_period") or {}
    if months and (bp.get("start"), bp.get("end"), bp.get("current")) != (months[0], months[-1], months[-1]):
        errors.append("billing_period does not match the billing records")
    if not resources:
        errors.append("dataset has no resources")
    ids = [r.get("id") for r in resources]
    if len(ids) != len(set(ids)) or not all(ids):
        errors.append("resource ids must be present and unique")
    for r in resources:
        if r.get("service") not in SERVICES:
            errors.append(f"resource {r.get('id')} has unknown service {r.get('service')!r}")
        mc = r.get("monthly_cost")
        if not isinstance(mc, (int, float)) or not math.isfinite(mc) or mc < 0:
            errors.append(f"resource {r.get('id')} has invalid monthly_cost {mc!r}")
        if not isinstance(r.get("metrics"), dict):
            errors.append(f"resource {r.get('id')} has no metrics object")
    if not errors and ds.get("dataset_id") != content_hash(ds.get("seed", SEED), spend, resources, (ds.get("scenario") or {}).get("id", SCENARIO["id"])):
        errors.append("dataset_id does not match the dataset content")
    return errors


def get_dataset(snapshot_id: str | None = None) -> dict:
    """A deep copy of the active (or a specific) persisted snapshot."""
    from .snapshots import load_dataset
    return load_dataset(snapshot_id)


def dataset_meta(snapshot_id: str | None = None) -> dict:
    from .snapshots import snapshot_meta
    return snapshot_meta(snapshot_id)
