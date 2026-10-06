"""用默认模拟适配器离线验证完整准备图；不可达简历 URL 用于测试读取失败回退。"""

from __future__ import annotations

import asyncio

from app.dependencies.container import build_deps
from app.schemas.shared_models import InterviewContext, LanguageMode, PrepRequest
from app.services.prep.pipeline import run_prep


def _request(primary: str = "en", mixed: bool = False) -> PrepRequest:
    return PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary=primary, mixed=mixed),
    )


def test_run_prep_produces_ready_interview_context() -> None:
    deps = build_deps()
    session_id = asyncio.run(run_prep(_request(), deps))

    assert session_id
    assert session_id.startswith("sess_")

    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    assert isinstance(ctx, InterviewContext)
    assert ctx.session_id == session_id

    assert ctx.candidate is not None
    assert ctx.job is not None
    assert ctx.company is not None
    assert ctx.gap is not None
    assert ctx.plan is not None

    assert ctx.plan.questions, "expected a non-empty question plan"
    for q in ctx.plan.questions:
        assert 1 <= q.difficulty <= 5, f"difficulty {q.difficulty} out of 1..5"
        assert q.text.get("en"), "question text must include an 'en' entry"
        assert q.followups, "each question needs >= 1 seeded followup"
        assert q.target_competency, "each question needs a target_competency"
        assert q.rubric, "each question needs >= 1 rubric item"

    assert deps.repo.get_status(session_id) == "ready"


def test_run_prep_pins_language_mode_for_non_english() -> None:
    deps = build_deps()
    session_id = asyncio.run(run_prep(_request(primary="vi", mixed=True), deps))

    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    # 计划的语言设置必须来自请求，避免模型回显改变语音路由。
    assert ctx.plan.language_mode.primary == "vi"
    assert ctx.plan.language_mode.mixed is True


def test_run_prep_company_intel_has_no_citations() -> None:
    deps = build_deps()
    session_id = asyncio.run(run_prep(_request(), deps))

    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    assert "citations" not in ctx.company.model_dump()


class _RecordingKnowledge:
    """记录知识入库键和资料的适配器替身。"""

    def __init__(self) -> None:
        self.ingests: list[tuple[str, list[str]]] = []

    async def search(self, user_id: str, query: str, lang: str):
        return ("", [])

    async def ingest(self, user_id: str, files: list[str]) -> str:
        self.ingests.append((user_id, list(files)))
        return f"trk-{user_id}-{len(files)}"


def test_run_prep_ingests_materials_keyed_by_session_id(monkeypatch) -> None:
    """准备资料必须按 session_id 入库，与后续教练检索键保持一致。"""
    deps = build_deps()
    recorder = _RecordingKnowledge()
    monkeypatch.setattr(deps, "knowledge", recorder)

    session_id = asyncio.run(run_prep(_request(), deps))

    assert recorder.ingests, "prep must ingest the prep materials"
    key, files = recorder.ingests[0]
    # 以 session_id 作为知识分区键，不使用用户身份 ID。
    assert key == session_id
    blob = "\n\n".join(files)
    assert "CANDIDATE CV" in blob
    assert "JOB DESCRIPTION" in blob
    # 验证入库载荷包含职位正文，避免只写入标题。
    assert "distributed payment systems" in blob


def test_run_prep_ingest_failure_does_not_break_prep(monkeypatch) -> None:
    """知识入库失败不能把已成功准备的会话变为 error。"""
    deps = build_deps()

    class _BoomKnowledge(_RecordingKnowledge):
        async def ingest(self, user_id: str, files: list[str]) -> str:
            raise RuntimeError("kb sidecar down")

    monkeypatch.setattr(deps, "knowledge", _BoomKnowledge())
    session_id = asyncio.run(run_prep(_request(), deps))
    assert deps.repo.get_status(session_id) == "ready"


def test_planner_timeout_warning_identifies_cause_and_pins_language(monkeypatch) -> None:
    from app.core.adapters.mock import build_mock
    from app.schemas.shared_models import (
        CandidateProfile,
        CompanyIntel,
        GapAnalysis,
        JobSpec,
    )
    from app.services.prep.nodes import question_planner

    deps = build_deps()

    class TimeoutLLM:
        async def complete_json(self, **kwargs):
            raise TimeoutError()

    monkeypatch.setattr(deps, "llm", TimeoutLLM())
    req = _request(primary="zh")

    async def exercise():
        sid = await deps.repo.create_session(req)
        result = await question_planner({
            "req": req, "session_id": sid,
            "candidate": build_mock(CandidateProfile), "job": build_mock(JobSpec),
            "company": build_mock(CompanyIntel), "gap": build_mock(GapAnalysis),
        }, deps)
        view = await deps.repo.get_session_view(sid)
        return result["plan"], view

    plan, view = asyncio.run(exercise())
    assert plan.language_mode == req.language_mode
    assert any("timed out" in warning for warning in view.prep_warnings)
    assert "question_planner" in view.progress
