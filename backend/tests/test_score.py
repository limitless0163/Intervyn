"""用模拟准备流程生成会话，再保存回答并端到端验证评分、状态及降级行为。

回答通过上下文写回，以明确测试输入；仓库追加回答方法也会同步权威上下文。
"""

from __future__ import annotations

import asyncio

from app.dependencies.container import build_deps
from app.schemas.shared_models import (
    AnswerRecord,
    InterviewContext,
    LanguageMode,
    PrepRequest,
    ScoreCard,
    ScoreRequest,
)
from app.services.post import run_score
from app.services.prep import run_prep


def _request(primary: str = "en", mixed: bool = False) -> PrepRequest:
    return PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary=primary, mixed=mixed),
    )


def _answer_for(question_id: str, n: int) -> AnswerRecord:
    return AnswerRecord(
        question_id=question_id,
        transcript=(
            f"Well, um, for question {n} I would start by clarifying the requirements, "
            "then I designed a service that, you know, handled retries and idempotency."
        ),
        started_at="2026-06-08T09:00:00Z",
        ended_at="2026-06-08T09:02:00Z",
        duration_sec=120.0,
    )


def _seed_answers(session_id: str, deps, count: int = 3) -> InterviewContext:
    """按计划中的真实题号追加指定数量的答案，并保存上下文。"""
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    questions = ctx.plan.questions
    assert questions, "prep should yield at least one planned question"
    for i, question in enumerate(questions[:count], start=1):
        ctx.answers.append(_answer_for(question.id, i))
    asyncio.run(deps.repo.save_context(session_id, ctx))
    return ctx


def _prepare_session(deps) -> tuple[str, InterviewContext]:
    session_id = asyncio.run(run_prep(_request(), deps))
    ctx = _seed_answers(session_id, deps)
    return session_id, ctx


def _assert_valid_scorecard(sc: ScoreCard, ctx: InterviewContext) -> None:
    assert isinstance(sc, ScoreCard)

    assert sc.competency_scores, "expected at least one competency score"
    for cs in sc.competency_scores:
        assert 0.0 <= cs.score <= 5.0, f"score {cs.score} out of 0..5"
        assert cs.level in {"weak", "developing", "solid", "strong"}

    assert 0.0 <= sc.overall_score <= 5.0

    # 评分能力须对应计划中的目标能力。
    plan_competencies = {q.target_competency for q in ctx.plan.questions}
    for cs in sc.competency_scores:
        assert cs.competency in plan_competencies, (
            f"competency {cs.competency!r} not in plan target_competencies"
        )

    # 弱项只能来自已评估能力。
    scored = {cs.competency for cs in sc.competency_scores}
    assert set(sc.weak_competencies) <= scored

    # 此场景全部作答，每题应有示范答案。
    answered_ids = {ma.question_id for ma in sc.model_answers}
    assert answered_ids == {q.id for q in ctx.plan.questions}

    assert 0.0 <= sc.language_report.fluency_score <= 5.0
    assert 0.0 <= sc.language_report.clarity_score <= 5.0
    assert sc.language_report.filler_word_count >= 0


def test_run_score_produces_valid_scorecard() -> None:
    deps = build_deps()
    session_id, ctx = _prepare_session(deps)

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    _assert_valid_scorecard(sc, ctx)
    assert deps.repo.get_status(session_id) == "complete"
    assert ScoreCard.model_validate(sc.model_dump()) == sc


def test_concurrent_scoring_evaluates_once_and_reuses_saved_card(monkeypatch) -> None:
    from app.services import post

    deps = build_deps()
    sid, _ = _prepare_session(deps)
    evaluate = post.evaluate
    calls = 0

    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def paused_evaluate(ctx, deps):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return await evaluate(ctx, deps)

        monkeypatch.setattr(post, "evaluate", paused_evaluate)
        req = ScoreRequest(session_id=sid)
        first = asyncio.create_task(run_score(req, deps))
        await entered.wait()
        others = [asyncio.create_task(run_score(req, deps)) for _ in range(7)]
        await asyncio.sleep(0)
        assert calls == 1
        release.set()
        cards = await asyncio.gather(first, *others)
        assert all(card == cards[0] for card in cards)
        assert calls == 1
        assert deps.repo.get_status(sid) == "complete"

    asyncio.run(run())


def test_run_score_competencies_map_to_plan() -> None:
    deps = build_deps()
    session_id, ctx = _prepare_session(deps)

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    plan_competencies = {q.target_competency for q in ctx.plan.questions}
    assert plan_competencies, "plan must define target competencies"
    assert {cs.competency for cs in sc.competency_scores} <= plan_competencies
    assert set(sc.weak_competencies) <= {cs.competency for cs in sc.competency_scores}


def test_run_score_is_stable_on_rerun() -> None:
    deps = build_deps()
    session_id, ctx = _prepare_session(deps)

    first = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))
    second = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    # 离线重复评分必须保持结构和值一致。
    assert first.model_dump() == second.model_dump()
    _assert_valid_scorecard(second, ctx)
    assert deps.repo.get_status(session_id) == "complete"


def test_run_score_handles_missing_context() -> None:
    deps = build_deps()
    # 不存在的会话返回空结果，不生成虚假成绩。
    sc = asyncio.run(run_score(ScoreRequest(session_id="sess_does_not_exist"), deps))

    assert isinstance(sc, ScoreCard)
    assert sc.competency_scores == []
    assert sc.weak_competencies == []
    assert sc.overall_score == 0.0
    assert sc.coverage_pct == 0.0
    assert ScoreCard.model_validate(sc.model_dump()) == sc


def test_run_score_skips_when_no_answers() -> None:
    """没有回答时标记 no_answers，不持久化已完成的零分报告。"""
    deps = build_deps()
    session_id = asyncio.run(run_prep(_request(), deps))
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None and ctx.answers == []

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    assert isinstance(sc, ScoreCard)
    assert sc.competency_scores == []
    assert sc.overall_score == 0.0
    assert sc.coverage_pct == 0.0
    assert ScoreCard.model_validate(sc.model_dump()) == sc
    assert deps.repo.get_status(session_id) == "no_answers"


def test_run_score_skips_when_all_answers_are_blank() -> None:
    """空白答案记录也属于无回答，不能仅凭列表非空进入评分。"""
    deps = build_deps()
    session_id = asyncio.run(run_prep(_request(), deps))
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    question_id = ctx.plan.questions[0].id
    for blank in ("", "   "):
        ctx.answers.append(
            AnswerRecord(
                question_id=question_id, transcript=blank, started_at="", ended_at=""
            )
        )
    asyncio.run(deps.repo.save_context(session_id, ctx))
    assert ctx.answers, "precondition: the answers list itself is non-empty"

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    assert isinstance(sc, ScoreCard)
    assert sc.competency_scores == []
    assert sc.overall_score == 0.0
    assert sc.coverage_pct == 0.0
    # 无回答会话保留 no_answers，不保存成绩单。
    assert deps.repo.get_status(session_id) == "no_answers"
    assert deps.repo._rows[session_id].scorecard is None


def test_run_score_reports_partial_coverage() -> None:
    """未回答题目降低覆盖率，但不得计为弱能力。"""
    deps = build_deps()
    session_id, ctx = _prepare_session(deps)

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    answered_ids = {a.question_id for a in ctx.answers if a.transcript and a.transcript.strip()}
    total = len(ctx.plan.questions)
    expected = len(answered_ids) / total if total else 1.0
    assert abs(sc.coverage_pct - expected) < 1e-9

    # 未探查的能力不能生成分数或弱项。
    answered_comps = {q.target_competency for q in ctx.plan.questions if q.id in answered_ids}
    assert set(sc.weak_competencies) <= answered_comps
    assert {cs.competency for cs in sc.competency_scores} <= answered_comps


def test_run_score_errors_when_evaluate_stage_fails(monkeypatch) -> None:
    """整体能力评估失败时标记可重试的 error，返回空结果但不保存零分报告。"""
    deps = build_deps()
    session_id, _ctx = _prepare_session(deps)

    from app.services import post

    async def _boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(post, "evaluate", _boom)

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    assert isinstance(sc, ScoreCard)
    assert sc.competency_scores == []
    assert ScoreCard.model_validate(sc.model_dump()) == sc
    assert deps.repo.get_status(session_id) == "error"
    assert deps.repo._rows[session_id].scorecard is None


def test_run_score_degrades_when_a_late_stage_fails(monkeypatch) -> None:
    """叙述阶段失败时仍保存已完成的降级报告，保留能力分数。"""
    deps = build_deps()
    session_id, _ctx = _prepare_session(deps)

    from app.services import post

    async def _boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(post, "generate_report", _boom)

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    assert isinstance(sc, ScoreCard)
    assert sc.competency_scores
    assert ScoreCard.model_validate(sc.model_dump()) == sc
    assert deps.repo.get_status(session_id) == "complete"
