"""通过 TestClient 离线验证学习计划与教练聊天接口。"""

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _scorecard_body(weak: list[str]) -> dict:
    comp = [
        {"competency": c, "score": 1.5, "evidence": f"struggled with {c}", "level": "weak"}
        for c in weak
    ]
    return {
        "overall_score": 1.5,
        "competency_scores": comp,
        "strengths": [],
        "weaknesses": list(weak),
        "weak_competencies": list(weak),
        "model_answers": [],
        "next_steps": [],
        "language_report": {
            "fluency_score": 3.0,
            "filler_word_count": 1,
            "clarity_score": 3.0,
            "code_switching_notes": "",
            "pronunciation_notes": "",
            "summary": "ok",
        },
        "summary": "test",
    }


def test_coach_plan_endpoint() -> None:
    resp = _client().post(
        "/api/coach/plan",
        json={"scorecard": _scorecard_body(["System Design", "Leadership"])},
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert {m["competency"] for m in plan["modules"]} == {"System Design", "Leadership"}
    assert plan["total_min"] == sum(m["est_min"] for m in plan["modules"])


def test_coach_chat_endpoint() -> None:
    resp = _client().post(
        "/api/coach/chat",
        json={"session_id": "sess_x", "query": "How do I structure a STAR answer?", "lang": "en"},
    )
    assert resp.status_code == 200
    reply = resp.json()
    assert isinstance(reply["answer"], str) and reply["answer"]
    # 未配置知识检索时不返回模拟引用。
    assert reply["citations"] == []
    assert len(reply["follow_ups"]) <= 3


def test_coach_rejects_large_inputs_before_building_dependencies(monkeypatch):
    from app.api.routes import coach

    def unexpected():
        raise AssertionError("large inputs must not trigger external services")

    monkeypatch.setattr(coach, "build_deps", unexpected)
    with _client() as client:
        response = client.post("/api/coach/chat", json={
            "session_id": "sess_x", "query": "x" * 10_001, "lang": "en",
        })
        assert response.status_code == 413
        response = client.post("/api/coach/plan", json={
            "scorecard": _scorecard_body([f"skill{i}" for i in range(101)]),
        })
        assert response.status_code == 413
