"""验证评分请求先被接受，慢报告后台执行且已有分数保留。"""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.api.routes import score as score_api
from app.dependencies.container import build_deps
from app.schemas.shared_models import ScoreRequest
from app.services.post.report import generate_report

from .test_score import _prepare_session


def test_background_dispatch_returns_before_scoring_and_deduplicates(monkeypatch):
    deps = build_deps()
    sid, _ = _prepare_session(deps)
    calls = []

    async def slow_score(req, deps):
        calls.append(req.session_id)

    monkeypatch.setattr(score_api, "run_score", slow_score)

    async def run():
        tasks = BackgroundTasks()
        result = await score_api.start_score(ScoreRequest(session_id=sid), tasks)
        assert result["status"] == "scoring"
        assert calls == []
        view = await deps.repo.get_session_view(sid)
        assert view.status == "scoring"
        repeated = BackgroundTasks()
        await score_api.start_score(ScoreRequest(session_id=sid), repeated)
        assert not repeated.tasks
        await tasks()
        assert calls == [sid]
        # 持久化 scoring 状态可能陈旧，无进程内任务时须允许重试。
        retry = BackgroundTasks()
        await score_api.start_score(ScoreRequest(session_id=sid), retry)
        assert retry.tasks
        await retry()
        assert calls == [sid, sid]

    asyncio.run(run())


def test_slow_model_answer_does_not_discard_narrative_or_other_answers():
    deps = build_deps()
    _, ctx = _prepare_session(deps)
    question = ctx.plan.questions[0]
    other = question.model_copy(update={"id": "fast"})
    ctx.plan.questions.append(other)
    ctx.answers.append(ctx.answers[0].model_copy(update={"question_id": "fast"}))
    started = 0

    async def text(**kwargs):
        nonlocal started
        started += 1
        if started == 1:
            await asyncio.Event().wait()
        return "An improved answer that completed in time."

    async def json_reply(**kwargs):
        return kwargs["schema"](
            strengths=["A retained strength"], weaknesses=["A retained weakness"],
            next_steps=["Keep practicing"], summary="The narrative survived.",
        )

    fast_deps = replace(
        deps, llm=SimpleNamespace(complete_text=text, complete_json=json_reply),
        settings=deps.settings.model_copy(update={"score_stage_timeout_sec": 0.05}),
    )
    from app.services.post.language_coach import coach

    language_report = asyncio.run(coach(ctx, deps))
    card = asyncio.run(generate_report(ctx, [], language_report, fast_deps))
    assert card.summary == "The narrative survived."
    assert card.strengths == ["A retained strength"]
    assert [a.question_id for a in card.model_answers] == ["fast"]
