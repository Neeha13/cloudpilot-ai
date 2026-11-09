"""Single source of truth for the synthetic demo dataset.

Every API (dashboard, anomalies, recommendations, copilot) reads the same
snapshot so that figures can never disagree between screens. The snapshot is
built once per process and identified by a content hash (``dataset_id``), which
recommendation events and copilot answers reference.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from datetime import date, datetime, timezone
from functools import lru_cache

SEED = 17

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


def _build_spend(ref: date) -> list[dict]:
    rng = random.Random(SEED)
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


@lru_cache(maxsize=1)
def _snapshot() -> dict:
    ref = date.today()
    spend = _build_spend(ref)
    resources = _build_resources()
    months = sorted({row["month"] for row in spend})
    digest = hashlib.sha256(
        json.dumps({"seed": SEED, "scenario": SCENARIO["id"], "spend": spend, "resources": resources},
                   sort_keys=True).encode()
    ).hexdigest()[:10]
    return {
        "dataset_id": f"ds-{digest}",
        "scenario": SCENARIO,
        "data_source": "synthetic_demo",
        "data_source_label": "Synthetic demo data",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "billing_period": {"start": months[0], "end": months[-1], "current": months[-1]},
        "spend": spend,
        "resources": resources,
    }


def get_dataset() -> dict:
    """A deep copy of the shared snapshot, so callers can never mutate it."""
    return copy.deepcopy(_snapshot())


def dataset_meta() -> dict:
    snap = _snapshot()
    return {k: v for k, v in snap.items() if k not in ("spend", "resources")} | {
        "resource_count": len(snap["resources"]),
        "spend_rows": len(snap["spend"]),
    }
