"""跨准备、回写、评分与教练的离线 API 流程；保留真实路由和业务流程。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.schemas.shared_models import CoachReply, ScoreResponse, StudyPlan
from app.schemas.views import PROGRESS_STEPS, SessionView

PREP = {
    "cv_url": "Backend engineer building reliable payment platforms and distributed systems.",
    "jd_text": "Senior backend engineer designing distributed payment systems in Python.",
    "company": "ExampleCorp",
    "language_mode": {"primary": "en", "mixed": False},
}


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def prepare(client):
    response = client.post("/api/prep", json=PREP)
    assert response.status_code == 200
    sid = response.json()["session_id"]
    view = SessionView.model_validate(client.get(f"/api/session/{sid}").json())
    assert view.status == "ready"
    assert set(view.progress) == set(PROGRESS_STEPS)
    assert view.context is not None
    return sid, view.context.model_dump(mode="json")


def test_interview_to_report_and_coaching(client):
    sid, context = prepare(client)
    question = context["plan"]["questions"][0]
    context["answers"] = [{
        "question_id": question["id"],
        "transcript": "I designed idempotency keys for payment retries and reduced duplicate writes.",
        "started_at": "2026-10-05T00:00:00Z", "ended_at": "2026-10-05T00:01:00Z",
    }]
    live = {"context": context, "transcript": [{"role": "user", "text": "payment retries"}]}
    assert client.post(f"/api/session/{sid}/live-result", json=live).status_code == 200

    response = client.post("/api/score/start", json={"session_id": sid})
    assert response.status_code == 202
    view = SessionView.model_validate(client.get(f"/api/session/{sid}").json())
    assert view.status == "complete"
    assert view.scorecard is not None
    assert view.scorecard.competency_scores
    assert view.scorecard.coverage_pct == 1 / len(context["plan"]["questions"])
    assert view.context.answers[0].transcript == context["answers"][0]["transcript"]

    # 再次评分返回同一报告，迟到的实时写入不得覆盖完成态与答案。
    repeat = client.post("/api/score", json={"session_id": sid})
    assert repeat.status_code == 200
    assert ScoreResponse.model_validate(repeat.json()).scorecard == view.scorecard
    live["context"]["answers"] = []
    assert client.post(f"/api/session/{sid}/live-result", json=live).status_code == 409
    assert client.get(f"/api/session/{sid}").json() == view.model_dump(mode="json")

    plan = client.post("/api/coach/plan", json={"scorecard": view.scorecard.model_dump()})
    assert plan.status_code == 200
    curriculum = StudyPlan.model_validate(plan.json())
    assert {module.competency for module in curriculum.modules} == set(
        view.scorecard.weak_competencies
    )
    assert curriculum.total_min == sum(module.est_min for module in curriculum.modules)
    chat = client.post("/api/coach/chat", json={"session_id": sid, "query": "How can I improve my answer?", "lang": "en"})
    assert chat.status_code == 200
    assert CoachReply.model_validate(chat.json()).answer


def test_silent_interview_has_no_persisted_scorecard(client):
    sid, context = prepare(client)
    context["answers"] = []
    assert client.post(f"/api/session/{sid}/live-result", json={"context": context, "status": "no_answers"}).status_code == 200
    assert client.post("/api/score/start", json={"session_id": sid}).status_code == 202
    view = client.get(f"/api/session/{sid}").json()
    assert view["status"] == "no_answers"
    assert view["scorecard"] is None


@pytest.mark.parametrize("path,body", [
    ("/api/prep", PREP),
    ("/api/score", {"session_id": "missing"}),
    ("/api/score/start", {"session_id": "missing"}),
    ("/api/coach/chat", {"session_id": "missing", "query": "Help", "lang": "en"}),
    ("/api/kb/query", {"store_key": "missing", "query": "Help", "lang": "en"}),
    ("/api/session/missing/coach-transcript", {"transcript": []}),
])
def test_internal_secret_protects_computation_and_writes(client, monkeypatch, path, body):
    monkeypatch.setenv("INTERNAL_API_SECRET", "test-secret")
    get_settings.cache_clear()
    for headers in ({}, {"X-Internal-Secret": "wrong-secret"}):
        assert client.post(path, json=body, headers=headers).status_code == 401
    # 健康与会话读路径仍可匿名访问。
    assert client.get("/health").status_code == 200
    assert client.get("/api/session/missing").status_code == 404


def test_valid_internal_secret_allows_full_prep(client, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "test-secret")
    get_settings.cache_clear()
    client.headers["X-Internal-Secret"] = "test-secret"
    prepare(client)
