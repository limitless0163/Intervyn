"""用可控的故障及并发交错验证后端边界，不访问真实提供方。"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.api.routes import score as score_api
from app.core.adapters.llm import GeminiLLM, OpenAILLM
from app.core.adapters.mock import build_mock
from app.core.config import Settings
from app.dependencies import auth
from app.dependencies.container import build_deps
from app.schemas.shared_models import AnswerRecord, CompetencyScore, ScoreRequest
from app.services.post.evaluator import evaluate
from app.services.post.pipeline import run_score
from app.services.session import SessionConflictError, save_live_result

from .test_coach import _scorecard
from .test_score import _prepare_session


@pytest.mark.parametrize("field", [
    "local_probe_timeout_sec", "local_provider_timeout_sec", "llm_call_timeout_sec",
    "company_research_timeout_sec", "score_stage_timeout_sec", "score_verifier_timeout_sec",
    "shutdown_process_timeout_sec", "max_interview_duration_sec", "max_interview_turns",
])
def test_non_positive_runtime_limits_are_rejected(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_invalid_grace_and_flush_limits_are_rejected(value):
    for field in ("interview_answer_grace_sec", "transcript_flush_interval_sec"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{field: value})


def test_zero_grace_and_disabled_checkpoints_remain_supported():
    settings = Settings(_env_file=None, interview_answer_grace_sec=0, transcript_flush_interval_sec=0)
    assert settings.interview_answer_grace_sec == settings.transcript_flush_interval_sec == 0


def test_unicode_secret_mismatch_returns_401(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None, internal_api_secret="key"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.require_internal_secret("错误"))
    assert error.value.status_code == 401


def test_scoring_rejects_late_live_writes_and_keeps_snapshot(monkeypatch):
    from app.services.post import pipeline

    deps = build_deps()
    sid, ctx = _prepare_session(deps)
    original_evaluate = pipeline.evaluate

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        async def paused_evaluate(context, deps):
            entered.set()
            await release.wait()
            return await original_evaluate(context, deps)

        monkeypatch.setattr(pipeline, "evaluate", paused_evaluate)
        task = asyncio.create_task(run_score(ScoreRequest(session_id=sid), deps))
        await entered.wait()
        assert (await deps.repo.get_session_view(sid)).status == "scoring"
        with pytest.raises(SessionConflictError):
            await save_live_result(sid, ctx.model_copy(update={"answers": []}), [], None, deps.repo)
        assert await deps.repo.load_context(sid) == ctx
        release.set()
        card = await task
        assert card.competency_scores
        assert (await deps.repo.get_session_view(sid)).status == "complete"

    asyncio.run(exercise())


def test_cancelled_score_marks_retryable_error(monkeypatch):
    from app.services.post import pipeline

    deps = build_deps()
    sid, _ = _prepare_session(deps)

    async def exercise():
        entered = asyncio.Event()

        async def pending(*args):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(pipeline, "evaluate", pending)
        task = asyncio.create_task(run_score(ScoreRequest(session_id=sid), deps))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        view = await deps.repo.get_session_view(sid)
        assert view.status == "error"
        assert view.scorecard is None

    asyncio.run(exercise())


def test_unknown_question_answers_do_not_create_zero_scorecard():
    deps = build_deps()
    sid, ctx = _prepare_session(deps)
    ctx.answers = [AnswerRecord(question_id="unknown", transcript="A real answer", started_at="", ended_at="")]
    asyncio.run(deps.repo.save_context(sid, ctx))
    asyncio.run(run_score(ScoreRequest(session_id=sid), deps))
    view = asyncio.run(deps.repo.get_session_view(sid))
    assert view.status == "no_answers"
    assert view.scorecard is None


def test_evaluator_retains_fast_scores_when_one_call_hangs():
    deps = build_deps()
    _, ctx = _prepare_session(deps)
    question = ctx.plan.questions[0]
    ctx.plan.questions.append(question.model_copy(update={"id": "fast", "target_competency": "fast-skill"}))
    ctx.answers.append(ctx.answers[0].model_copy(update={"question_id": "fast"}))
    calls = 0

    async def complete_json(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.Event().wait()
        return build_mock(CompetencyScore)

    test_deps = replace(
        deps, llm=SimpleNamespace(complete_json=complete_json),
        settings=deps.settings.model_copy(update={"score_stage_timeout_sec": 0.05}),
    )
    scores = asyncio.run(evaluate(ctx, test_deps))
    assert [score.competency for score in scores] == ["fast-skill"]


def test_background_failure_cleanup_survives_repository_failure(monkeypatch):
    sid = "sess_failure_cleanup"

    async def boom(*args):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(score_api, "run_score", boom)
    deps = SimpleNamespace(repo=SimpleNamespace(get_session_view=boom))
    score_api._scheduled_scores.add(sid)
    asyncio.run(score_api._score_in_background(ScoreRequest(session_id=sid), deps))
    assert sid not in score_api._scheduled_scores


def test_background_dispatch_refuses_session_without_context(monkeypatch):
    deps = SimpleNamespace(repo=SimpleNamespace())

    async def get_view(sid):
        return SimpleNamespace(status="prep", context=None)

    deps.repo.get_session_view = get_view
    monkeypatch.setattr(score_api, "build_deps", lambda: deps)
    with pytest.raises(HTTPException) as error:
        asyncio.run(score_api.start_score(ScoreRequest(session_id="prep_only"), BackgroundTasks()))
    assert error.value.status_code == 409
    assert "prep_only" not in score_api._scheduled_scores


def test_coach_plan_has_bounded_concurrency_and_stable_order():
    from app.services.coach.pipeline import run_coach_plan

    deps = build_deps()
    scorecard = _scorecard([f"skill{i}" for i in range(9)])
    scorecard.weak_competencies.append("skill0")
    active = peak = 0

    async def draft(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return kwargs["schema"](title="Study", rationale="Practice", est_min=15)

    plan = asyncio.run(run_coach_plan(scorecard, replace(deps, llm=SimpleNamespace(complete_json=draft))))
    assert peak == 4
    assert [module.competency for module in plan.modules] == [f"skill{i}" for i in range(9)]
    assert plan.total_min == 9 * 15


@pytest.mark.parametrize("provider", [OpenAILLM, GeminiLLM])
@pytest.mark.parametrize("failure", [False, True])
def test_model_clients_close_on_success_and_failure(monkeypatch, provider, failure):
    closed = []

    async def response(**kwargs):
        if failure:
            raise RuntimeError("provider down")
        return SimpleNamespace(text="answer", choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))])

    async def close_async():
        closed.append("async")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=response)),
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=response), aclose=close_async),
        close=close_async if provider is OpenAILLM else lambda: closed.append("sync"),
    )
    adapter = provider("key", "test-model")
    monkeypatch.setattr(adapter, "_client", lambda: client)
    if failure:
        with pytest.raises(RuntimeError, match="provider down"):
            asyncio.run(adapter.complete_text(system="sys", user="user"))
    else:
        assert asyncio.run(adapter.complete_text(system="sys", user="user")) == "answer"
    assert "async" in closed
