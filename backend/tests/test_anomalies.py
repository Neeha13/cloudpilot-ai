import math

from app.anomalies import detect_all


def _dataset(series: dict[str, list[float]]):
    months = [f"2026-{m:02d}" for m in range(1, len(next(iter(series.values()))) + 1)]
    spend = [{"month": m, "service": s, "cost": c} for s, costs in series.items() for m, c in zip(months, costs) if c is not None]
    return {"spend": spend, "resources": [], "dataset_id": "ds-test", "generated_at": "2026-07-09T00:00:00+00:00"}


def _current(series):
    return [a for a in detect_all(_dataset(series)) if a["is_current"]]


# ------------------------------------------------------------- detector

def test_spike_detected_against_median_baseline():
    found = _current({"EC2": [100, 104, 98, 101, 99, 102, 160]})
    assert [a["type"] for a in found] == ["spike"]
    assert found[0]["severity"] == "High"
    assert found[0]["baseline"]["value"] == 100.5


def test_one_off_old_spike_does_not_inflate_baseline():
    # A median baseline ignores the single historic outlier, so the new jump is still caught.
    found = _current({"EC2": [100, 300, 98, 101, 99, 102, 140]})
    assert found and found[0]["type"] == "spike"


def test_normal_noise_is_not_flagged():
    assert _current({"S3": [100, 108, 95, 103, 97, 106, 101]}) == []


def test_gradual_growth_detected_not_as_spike():
    found = _current({"CloudWatch": [100, 101, 99, 100, 107, 114, 122]})
    assert [a["type"] for a in found] == ["gradual_growth"]
    assert found[0]["severity"] == "Low"
    assert len(found[0]["deviation"]["steps_percent"]) == 3


def test_new_service_detected():
    found = _current({"EC2": [100] * 7, "SageMaker": [None] * 6 + [180]})
    assert [(a["service"], a["type"]) for a in found] == [("SageMaker", "new_service")]


def test_severity_thresholds():
    assert _current({"EC2": [100, 101, 99, 100, 102, 98, 125]})[0]["severity"] == "Medium"
    assert _current({"EC2": [100, 101, 99, 100, 102, 98, 170]})[0]["severity"] == "Critical"


def test_detection_only_uses_data_available_at_the_time():
    # History must not change when later months are appended (walk-forward).
    base = {"EC2": [100, 104, 98, 101, 99, 102, 160]}
    longer = {"EC2": base["EC2"] + [400]}
    first = {a["id"]: a["deviation"] for a in detect_all(_dataset(base))}
    later = {a["id"]: a["deviation"] for a in detect_all(_dataset(longer)) if a["id"] in first}
    assert first == later


# ------------------------------------------------------------------ API

def test_every_anomaly_meets_acceptance_criteria(client):
    history = client.get("/api/anomalies/history").json()["anomalies"]
    assert history
    for a in history:
        assert a["baseline"]["value"] is not None
        assert a["baseline"]["observation_window"]["months"] >= 1
        assert a["deviation"]["percent"] is not None
        assert a["service"] and a["detected_at"] and a["status"]


def test_scenario_anomalies(client):
    current = {a["service"]: a for a in client.get("/api/anomalies").json()}
    assert current["EC2"]["type"] == "spike" and current["EC2"]["severity"] == "High"
    assert current["CloudWatch"]["type"] == "gradual_growth"
    assert set(current) == {"EC2", "CloudWatch"}


def test_current_anomalies_sorted_by_severity(client):
    sev = [a["severity"] for a in client.get("/api/anomalies").json()]
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    assert sev == sorted(sev, key=order.get)


def test_anomaly_cost_matches_dashboard(client):
    dash = client.get("/api/dashboard").json()
    for a in client.get("/api/anomalies").json():
        assert a["current_cost"] == dash["service_breakdown"][a["service"]]


def test_investigation_detail(client):
    aid = next(a["id"] for a in client.get("/api/anomalies").json() if a["service"] == "EC2")
    d = client.get(f"/api/anomalies/{aid}").json()
    inv = d["investigation"]
    assert inv["timeline"][-1]["cost"] == d["current_cost"]
    att = inv["attribution"]
    assert math.isclose(att["attributed_cost"] + att["unattributed_cost"], d["current_cost"], abs_tol=0.01)
    assert {r["resource_id"] for r in inv["related_recommendations"]} == {"i-demo-01", "i-demo-02"}
    assert inv["investigation_areas"]


def test_anomaly_lifecycle(client):
    aid = client.get("/api/anomalies").json()[0]["id"]
    act = lambda **b: client.post(f"/api/anomalies/{aid}/actions", json=b)
    assert act(action="acknowledge").json()["status"] == "acknowledged"
    assert act(action="acknowledge").status_code == 409
    assert act(action="resolve").status_code == 409  # resolution required
    body = act(action="resolve", resolution="expected_change", note="Planned launch").json()
    assert body["status"] == "resolved"
    assert body["lifecycle"]["resolution_label"].startswith("Expected change")
    assert [e["action"] for e in body["history"]] == ["resolve", "acknowledge"]
    assert act(action="reopen").json()["status"] == "open"


def test_history_summary_counts(client):
    aid = client.get("/api/anomalies").json()[0]["id"]
    client.post(f"/api/anomalies/{aid}/actions", json={"action": "resolve", "resolution": "fixed"})
    body = client.get("/api/anomalies/history").json()
    s = body["summary"]
    assert s["total"] == len(body["anomalies"])
    assert s["by_status"]["resolved"] == 1
    assert s["unresolved"] == s["total"] - 1
    assert sum(s["by_service"].values()) == s["total"]


def test_unknown_anomaly_404(client):
    assert client.get("/api/anomalies/anom-nope").status_code == 404


def test_copilot_anomaly_answer_is_grounded(client):
    body = client.post("/api/copilot", json={"question": "What is causing the EC2 anomaly?"}).json()
    card = body["cards"][0]
    assert card["type"] == "anomaly" and card["service"] == "EC2"
    assert card["severity"] == "High"
    assert "not proof" in body["answer"]
