"""验证结果回写先核对会话身份，拒绝请求不得修改已有记录。"""

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import session as session_api
from app.core.adapters.mock import build_mock
from app.dependencies.auth import require_internal_secret
from app.main import create_app
from app.repositories.repository import MemoryRepository
from app.schemas.shared_models import InterviewContext, LanguageMode, PrepRequest


def test_live_result_rejects_mismatched_context_without_writing(monkeypatch) -> None:
    repo = MemoryRepository()
    sid = asyncio.run(repo.create_session(PrepRequest(
        cv_url="Candidate profile", jd_text="Backend engineer", company="Acme",
        language_mode=LanguageMode(primary="en", mixed=False),
    )))
    original = build_mock(InterviewContext).model_copy(update={"session_id": sid})
    transcript = [{"role": "user", "text": "original answer"}]
    asyncio.run(repo.save_context(sid, original))
    asyncio.run(repo.save_transcript(sid, transcript))
    monkeypatch.setattr(session_api, "build_deps", lambda: SimpleNamespace(repo=repo))
    app = create_app()
    app.dependency_overrides[require_internal_secret] = lambda: None
    replacement = original.model_copy(update={"session_id": "sess_other", "answers": []})

    with TestClient(app) as client:
        response = client.post(f"/api/session/{sid}/live-result", json={
            "context": replacement.model_dump(),
            "transcript": [{"role": "user", "text": "wrong session"}],
            "status": "no_answers",
        })
        assert response.status_code == 422
        assert asyncio.run(repo.load_context(sid)) == original
        assert repo._rows[sid].transcript == transcript
        assert repo.get_status(sid) == "prep"

        response = client.post(f"/api/session/{sid}/live-result", json={
            "context": original.model_dump(), "transcript": transcript,
        })
        assert response.status_code == 200


def test_coach_transcript_api_writes_only_coach_history(monkeypatch):
    repo = MemoryRepository()
    sid = asyncio.run(repo.create_session(PrepRequest(
        cv_url="Candidate", jd_text="Backend engineer", company="Acme",
        language_mode=LanguageMode(primary="en", mixed=False),
    )))
    interview = [{"role": "user", "text": "interview"}]
    asyncio.run(repo.save_transcript(sid, interview))
    asyncio.run(repo.update_status(sid, "complete"))
    monkeypatch.setattr(session_api, "build_deps", lambda: SimpleNamespace(repo=repo))
    app = create_app()
    app.dependency_overrides[require_internal_secret] = lambda: None
    with TestClient(app) as client:
        coaching = [{"role": "user", "text": "coach question"}]
        response = client.post(f"/api/session/{sid}/coach-transcript", json={"transcript": coaching})
        assert response.status_code == 200
        assert repo._rows[sid].transcript == interview
        assert repo._rows[sid].coach_transcript == coaching
        assert repo.get_status(sid) == "complete"
        assert client.post("/api/session/missing/coach-transcript", json={"transcript": []}).status_code == 404
