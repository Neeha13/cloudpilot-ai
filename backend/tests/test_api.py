import math
from datetime import date

from app.dataset import _month_start
from app.recommendations import WEIGHTS


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_has_spend(client):
    data = client.get("/api/dashboard").json()
    assert data["total_spend"] > 0
    assert len(data["monthly_trend"]) >= 2


# ---------------------------------------------------------- data consistency

def test_dashboard_totals_reconcile_with_services(client):
    data = client.get("/api/dashboard").json()
    assert math.isclose(sum(data["service_breakdown"].values()), data["total_spend"], abs_tol=0.01)
    assert data["monthly_trend"][-1]["total"] == data["total_spend"]


def test_all_apis_share_one_dataset_snapshot(client):
    dash = client.get("/api/dashboard").json()
    anomalies = client.get("/api/anomalies").json()
    recs = client.get("/api/recommendations").json()
    ids = {dash["dataset_id"], client.get("/api/dataset").json()["dataset_id"]}
    ids |= {a["dataset_id"] for a in anomalies} | {r["dataset_id"] for r in recs}
    assert len(ids) == 1
    ec2 = next(a for a in anomalies if a["service"] == "EC2")
    assert ec2["current_cost"] == dash["service_breakdown"]["EC2"]


def test_month_arithmetic_never_skips_a_month():
    # The v1 "today - 30 days" approach skipped February when run on 1 March.
    months = [_month_start(date(2026, 3, 1), k) for k in range(7)]
    assert [m.month for m in months] == [3, 2, 1, 12, 11, 10, 9]


# --------------------------------------------------- recommendation engine

def test_recommendations_are_explainable(client):
    data = client.get("/api/recommendations").json()
    assert len(data) > 0
    for r in data:
        assert r["evidence"] and r["verify_before_acting"] and r["risk"]["items"]
        assert r["detected"] and r["why_it_matters"] and r["suggested_action"]
        assert r["savings"]["kind"] == "estimate" and r["savings"]["formula"]
        assert len(r["confidence"]["factors"]) == 4


def test_savings_calculation_is_reproducible(client):
    resources = {x["id"]: x for x in client.get("/api/resources").json()}
    for r in client.get("/api/recommendations").json():
        s = r["savings"]
        expected = round(resources[r["resource_id"]]["monthly_cost"] * s["inputs"]["reduction_rate"], 2)
        assert s["monthly"] == expected
        assert s["annual"] == round(expected * 12, 2)


def test_priority_score_matches_weighted_formula(client):
    for r in client.get("/api/recommendations").json():
        f = r["priority"]["factors"]
        assert all(0 <= v <= 100 for v in f.values())
        assert math.isclose(r["priority"]["score"], round(sum(WEIGHTS[k] * f[k] for k in WEIGHTS), 1))


def test_recommendations_sorted_by_priority(client):
    scores = [r["priority"]["score"] for r in client.get("/api/recommendations").json()]
    assert scores == sorted(scores, reverse=True)


def test_missing_evidence_caps_confidence(client):
    recs = {r["resource_id"]: r for r in client.get("/api/recommendations").json()}
    ec2 = recs["i-demo-01"]  # memory metrics not collected
    assert "memory utilization" in ec2["confidence"]["missing_evidence"]
    assert ec2["confidence"]["level"] != "High"


def test_bursty_instance_gets_lower_confidence(client):
    recs = {r["resource_id"]: r for r in client.get("/api/recommendations").json()}
    assert recs["i-demo-02"]["confidence"]["score"] < recs["i-demo-01"]["confidence"]["score"]


def test_busy_instance_is_not_flagged(client):
    assert "i-demo-03" not in {r["resource_id"] for r in client.get("/api/recommendations").json()}


def test_production_database_is_high_risk(client):
    db = next(r for r in client.get("/api/recommendations").json() if r["resource_id"] == "db-demo-01")
    assert db["risk"]["level"] == "High"
    assert "Production workload" in db["risk"]["drivers"]


# ------------------------------------------------------------- lifecycle

def _act(client, rec_id, **body):
    return client.post(f"/api/recommendations/{rec_id}/actions", json=body)


def test_new_recommendations_start_open(client):
    assert all(r["status"] == "open" for r in client.get("/api/recommendations").json())


def test_full_lifecycle_and_history(client):
    rid = "rec-vol-demo-01"
    assert _act(client, rid, action="investigate").json()["status"] == "investigating"
    assert _act(client, rid, action="plan").json()["status"] == "planned"
    body = _act(client, rid, action="implement").json()
    assert body["status"] == "implemented"
    assert [e["action"] for e in body["history"]] == ["implement", "plan", "investigate"]
    assert body["history"][0]["estimated_monthly_savings"] == body["savings"]["monthly"]
    assert _act(client, rid, action="reopen").json()["status"] == "open"


def test_invalid_transition_rejected(client):
    assert _act(client, "rec-vol-demo-01", action="implement").status_code == 409


def test_dismiss_requires_reason(client):
    assert _act(client, "rec-db-demo-01", action="dismiss").status_code == 409
    assert _act(client, "rec-db-demo-01", action="dismiss", reason="other").status_code == 409
    ok = _act(client, "rec-db-demo-01", action="dismiss", reason="business_critical")
    assert ok.status_code == 200
    assert ok.json()["lifecycle"]["reason_label"] == "Resource is business-critical"


def test_unknown_reason_rejected(client):
    assert _act(client, "rec-db-demo-01", action="dismiss", reason="because").status_code == 422


def test_snooze_sets_expiry(client):
    body = _act(client, "rec-i-demo-01", action="snooze", snooze_days=7).json()
    assert body["status"] == "snoozed" and body["lifecycle"]["snooze_until"]


def test_unknown_recommendation_404(client):
    assert _act(client, "rec-nope", action="investigate").status_code == 404


def test_status_persists_across_requests(client):
    _act(client, "rec-i-demo-02", action="investigate")
    recs = {r["id"]: r for r in client.get("/api/recommendations").json()}
    assert recs["rec-i-demo-02"]["status"] == "investigating"


def test_v1_feedback_endpoint_maps_to_lifecycle(client):
    assert client.post("/api/recommendations/rec-i-demo-01/feedback", json={"decision": "accepted"}).status_code == 200
    recs = {r["id"]: r for r in client.get("/api/recommendations").json()}
    assert recs["rec-i-demo-01"]["status"] == "investigating"


def test_analytics_reflect_decisions(client):
    _act(client, "rec-vol-demo-01", action="investigate")
    _act(client, "rec-db-demo-01", action="dismiss", reason="business_critical")
    a = client.get("/api/recommendations/analytics").json()
    assert a["decision_coverage"]["decided"] == 2
    assert a["acceptance_rate"] == 0.5
    assert a["dismissal_reasons"] == {"Resource is business-critical": 1}
    assert a["savings_monthly"]["in_progress"] == 42.0
    s = a["savings_monthly"]
    parts = s["open"] + s["in_progress"] + s["implemented_unverified"] + s["dismissed"] + s["snoozed"]
    assert math.isclose(parts, s["potential_total"], abs_tol=0.01)


def test_scoring_model_is_published(client):
    m = client.get("/api/recommendations/model").json()
    assert math.isclose(sum(m["weights"].values()), 1.0)
    assert "business_critical" in m["dismiss_reasons"]


# --------------------------------------------------------------- copilot

def test_copilot_fallback(client):
    response = client.post("/api/copilot", json={"question": "Which service costs the most?"})
    assert response.status_code == 200
    assert response.json()["answer"]


def test_copilot_top_pick_uses_engine_figures(client):
    recs = client.get("/api/recommendations").json()
    body = client.post("/api/copilot", json={"question": "What should I investigate first?"}).json()
    card = body["cards"][0]
    assert card["id"] == recs[0]["id"]
    assert card["monthly_savings"] == recs[0]["savings"]["monthly"]
    assert body["sources"]


def test_copilot_explains_specific_resource(client):
    body = client.post("/api/copilot", json={"question": "Why was i-demo-01 flagged?"}).json()
    assert body["cards"][0]["resource_id"] == "i-demo-01"
    assert "memory utilization" in body["answer"]


def test_copilot_high_risk_filter(client):
    body = client.post("/api/copilot", json={"question": "Show me high-risk recommendations"}).json()
    assert body["cards"] and all(c["risk_level"] == "High" for c in body["cards"])
