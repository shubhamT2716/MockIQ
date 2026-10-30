RESUME = """Rahul Sharma - Backend Engineer, 3 years. Skills: Java, Spring, Kafka, Redis, AWS, SQL.
Payments service: reduced API latency by 40% using Redis caching; built Kafka consumers for settlement."""


def test_full_flow_via_api(client):
    packs = client.get("/api/role-packs").json()
    assert any(p["slug"] == "backend-sde" for p in packs)

    prof = client.post("/api/profiles", data={"text": RESUME})
    assert prof.status_code == 200, prof.text
    pid = prof.json()["id"]

    s = client.post("/api/sessions", json={"profile_id": pid, "role_pack": "backend-sde", "level": "L2",
                                           "stack": ["java-spring"], "rounds": [0, 3], "mode": "chat"}).json()
    sid = s["id"]
    assert [r["type"] for r in s["rounds"]] == ["DSA", "PROJECT_DEEP_DIVE"]

    start = client.post(f"/api/sessions/{sid}/start").json()
    assert start["messages"] and start["events"][0]["type"] == "round_started"
    again = client.post(f"/api/sessions/{sid}/start").json()  # idempotent
    assert again["messages"] == []

    assert client.get(f"/api/sessions/{sid}/report").status_code == 404
    status = "LIVE"
    for _ in range(200):
        r = client.post(f"/api/sessions/{sid}/turns", json={"text": "I'd use BFS and mark visited cells.",
                                                           "code": "def f(grid): pass"})
        assert r.status_code == 200, r.text
        status = r.json()["status"]
        if status == "COMPLETED":
            break
    assert status == "COMPLETED"
    rep = client.get(f"/api/sessions/{sid}/report").json()
    assert rep["status"] == "READY", rep
    body = rep["body"]
    assert body["verdict"] and len(body["rounds"]) == 2
    assert body["rounds"][0]["competencies"][0]["evidence"], "evidence should survive validation"
    assert client.post(f"/api/sessions/{sid}/turns", json={"text": "hello"}).status_code == 409
    assert client.post(f"/api/sessions/{sid}/report/rating", json={"rating": 4}).status_code == 204


def test_dashboard_after_interview_and_focus_mode(client):
    s = client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2", "rounds": [2], "mode": "chat"}).json()
    sid = s["id"]
    assert client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2", "focus_weak": True}).status_code == 422
    client.post(f"/api/sessions/{sid}/start")
    for _ in range(100):
        if client.post(f"/api/sessions/{sid}/turns", json={"text": "Use a cache and shard by key."}).json()["status"] == "COMPLETED":
            break
    d = client.get("/api/me/dashboard?tz_offset=-330").json()
    assert d["stats"]["completed"] == 1 and len(d["trend"]) == 1
    assert d["weak_topics"], "partial topics from the fake LLM should be recorded as weak"
    assert d["competencies"] and d["last_setup"] == {"role_pack": "backend-sde", "level": "L2"}
    f = client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2", "focus_weak": True})
    assert f.status_code == 200 and f.json()["focus"] == "weak"


def test_end_early_produces_report(client):
    s = client.post("/api/sessions", json={"role_pack": "qa-automation", "level": "L1", "mode": "voice"}).json()
    sid = s["id"]
    client.post(f"/api/sessions/{sid}/start")
    client.post(f"/api/sessions/{sid}/turns", json={"text": "Boundary values 17, 18, 60 and 61."})
    assert client.post(f"/api/sessions/{sid}/end").json()["status"] == "COMPLETED"
    rep = client.get(f"/api/sessions/{sid}/report").json()
    assert rep["status"] == "READY"
    assert len(rep["body"]["rounds"]) == 1 and rep["body"]["rounds_not_attempted"]


def test_validation_errors(client):
    assert client.post("/api/profiles", data={"text": "too short"}).status_code == 422
    assert client.post("/api/sessions", json={"role_pack": "nope", "level": "L2"}).status_code == 422
    assert client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "DIRECTOR"}).status_code == 422
    assert client.get("/api/sessions/does-not-exist").status_code == 404


def test_skip_command_via_api(client):
    s = client.post("/api/sessions", json={"role_pack": "backend-sde", "level": "L2", "rounds": [2]}).json()
    sid = s["id"]
    client.post(f"/api/sessions/{sid}/start")
    r = client.post(f"/api/sessions/{sid}/turns", json={"command": "skip"})
    assert r.status_code == 200 and r.json()["transcript"][-2]["text"] == "(Asked to skip this question.)"
    assert client.post(f"/api/sessions/{sid}/turns", json={"command": "dance"}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/turns", json={"text": "  "}).status_code == 422
    client.post(f"/api/sessions/{sid}/end")
    body = client.get(f"/api/sessions/{sid}/report").json()["body"]
    assert any(g["status"] == "SKIPPED" for g in body["missed_topics"])
    assert any(w["last_status"] == "SKIPPED" for w in client.get("/api/me/weak-topics").json())
