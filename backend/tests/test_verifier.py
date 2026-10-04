"""用显式新配置启用评分复核，避免修改共享缓存配置而污染其他测试。

模拟模型及内存仓库保证不依赖密钥或网络。
"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.dependencies.container import build_deps
from app.schemas.shared_models import (
    AnswerRecord,
    CompetencyScore,
    InterviewContext,
    LanguageMode,
    PrepRequest,
    ScoreCard,
    ScoreRequest,
)
from app.services.post.evaluator import evaluate, level_for_score
from app.services.post.pipeline import run_score, verify_scores
from app.services.prep.pipeline import run_prep


def _request() -> PrepRequest:
    return PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary="en", mixed=False),
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
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    questions = ctx.plan.questions
    assert questions, "prep should yield at least one planned question"
    for i, question in enumerate(questions[:count], start=1):
        ctx.answers.append(_answer_for(question.id, i))
    asyncio.run(deps.repo.save_context(session_id, ctx))
    return ctx


def _deps_with_verifier(enabled: bool):
    """创建显式开启复核的新依赖，不修改默认缓存。"""
    return build_deps(Settings(enable_score_verifier=enabled))


def _prepare(deps) -> tuple[str, InterviewContext]:
    session_id = asyncio.run(run_prep(_request(), deps))
    ctx = _seed_answers(session_id, deps)
    return session_id, ctx


def _assert_scores_consistent(scores: list[CompetencyScore]) -> None:
    assert scores, "expected at least one competency score"
    for cs in scores:
        assert 0.0 <= cs.score <= 5.0, f"score {cs.score} out of 0..5"
        # 等级必须与最终数值一致。
        assert cs.level == level_for_score(cs.score)
        assert cs.level in {"weak", "developing", "solid", "strong"}


def test_verify_scores_keeps_scores_in_range_and_levels_agree() -> None:
    deps = _deps_with_verifier(True)
    _, ctx = _prepare(deps)

    base = asyncio.run(evaluate(ctx, deps))
    verified = asyncio.run(verify_scores(ctx, base, deps))

    # 复核保留能力数量和顺序，并保证分数与等级一致。
    assert [cs.competency for cs in verified] == [cs.competency for cs in base]
    _assert_scores_consistent(verified)


def test_verify_scores_is_deterministic_and_never_raises() -> None:
    deps = _deps_with_verifier(True)
    _, ctx = _prepare(deps)

    base = asyncio.run(evaluate(ctx, deps))
    first = asyncio.run(verify_scores(ctx, base, deps))
    second = asyncio.run(verify_scores(ctx, base, deps))

    assert [cs.model_dump() for cs in first] == [cs.model_dump() for cs in second]


def test_run_score_with_verifier_on_produces_valid_scorecard() -> None:
    deps = _deps_with_verifier(True)
    session_id, _ = _prepare(deps)

    sc = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    assert isinstance(sc, ScoreCard)
    assert 0.0 <= sc.overall_score <= 5.0
    _assert_scores_consistent(sc.competency_scores)
    scored = {cs.competency for cs in sc.competency_scores}
    assert set(sc.weak_competencies) <= scored
    assert ScoreCard.model_validate(sc.model_dump()) == sc
    assert deps.repo.get_status(session_id) == "complete"


def test_run_score_with_verifier_on_is_stable_on_rerun() -> None:
    deps = _deps_with_verifier(True)
    session_id, _ = _prepare(deps)

    first = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))
    second = asyncio.run(run_score(ScoreRequest(session_id=session_id), deps))

    assert first.model_dump() == second.model_dump()


def test_verifier_off_is_a_noop() -> None:
    """关闭复核时结果须与直接能力评估一致。"""
    deps_off_a = _deps_with_verifier(False)
    session_a, _ = _prepare(deps_off_a)
    sc_off = asyncio.run(run_score(ScoreRequest(session_id=session_a), deps_off_a))

    ctx = asyncio.run(deps_off_a.repo.load_context(session_a))
    assert ctx is not None
    base = asyncio.run(evaluate(ctx, deps_off_a))
    assert [cs.model_dump() for cs in sc_off.competency_scores] == [
        cs.model_dump() for cs in base
    ]
