"""依次评估能力、分析语言并生成报告；各阶段独立降级，避免丢失已完成的评分。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ...core.tracing import add_event, start_span, start_trace
from ...schemas.shared_models import LanguageReport, ScoreCard
from ...utils.locks import KeyedLocks
from ..session import session_mutations
from .evaluator import evaluate
from .language_coach import coach
from .report import (
    _coverage_pct,
    _overall_score,
    _weak_competencies,
    generate_report,
)
from .verifier import verify_scores

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import CompetencyScore, InterviewContext, ScoreRequest

log = get_logger(__name__)

__all__ = ["coach", "evaluate", "generate_report", "run_score", "verify_scores"]


def _missing_context_scorecard(session_id: str) -> ScoreCard:
    """上下文缺失时返回契约有效的空结果，不保存为已完成评分。"""
    return ScoreCard(
        overall_score=0.0,
        competency_scores=[],
        strengths=[],
        weaknesses=[],
        weak_competencies=[],
        model_answers=[],
        next_steps=[],
        language_report=LanguageReport(
            fluency_score=0.0,
            filler_word_count=0,
            clarity_score=0.0,
            code_switching_notes="",
            pronunciation_notes="",
            summary="No interview context was found for this session.",
        ),
        summary=f"No interview context was found for session {session_id}; nothing to score.",
        coverage_pct=0.0,
    )


def _no_answers_scorecard(session_id: str) -> ScoreCard:
    """仅返回空结果，不保存成绩单；会话标记 no_answers，避免将未作答误报为零分。"""
    return ScoreCard(
        overall_score=0.0,
        competency_scores=[],
        strengths=[],
        weaknesses=[],
        weak_competencies=[],
        model_answers=[],
        next_steps=[],
        language_report=LanguageReport(
            fluency_score=0.0,
            filler_word_count=0,
            clarity_score=0.0,
            code_switching_notes="",
            pronunciation_notes="",
            summary="No answers were recorded for this interview.",
        ),
        summary=(
            f"No answers were recorded for session {session_id}; "
            "the interview ended before any question was answered."
        ),
        coverage_pct=0.0,
    )


def _fallback_language_report() -> LanguageReport:
    """语言评估失败时使用的中性降级报告。"""
    return LanguageReport(
        fluency_score=0.0,
        filler_word_count=0,
        clarity_score=0.0,
        code_switching_notes="",
        pronunciation_notes="",
        summary="Spoken-language assessment was unavailable for this interview.",
    )


def _degraded_scorecard(
    ctx: InterviewContext,
    comp_scores: list[CompetencyScore],
    lang_report: LanguageReport,
) -> ScoreCard:
    """报告生成失败时保留已算出的分数和覆盖率，返回部分成绩单。"""
    return ScoreCard(
        overall_score=_overall_score(comp_scores),
        competency_scores=comp_scores,
        strengths=[],
        weaknesses=[],
        weak_competencies=_weak_competencies(comp_scores),
        model_answers=[],
        next_steps=["Review the recorded answers and competency evidence."],
        language_report=lang_report,
        summary=(
            "Partial scorecard: detailed report generation was temporarily "
            "unavailable. Competency scores and interview coverage are preserved."
        ),
        coverage_pct=_coverage_pct(ctx),
    )


async def _guarded(coro, *, label: str, timeout: float):
    """限制单阶段耗时；超时或普通异常返回 None，由调用方选择降级结果。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        log.exception("post: scoring stage %r failed; degrading", label)
        return None


async def _maybe_distill_skill(session_id: str, deps: Deps) -> None:
    """启用后仅提出待审技能草稿；失败不影响成绩单，也不自动发布到正式库。"""
    if not deps.settings.enable_skill_distiller:
        return
    try:
        from ..skilllib.distiller import (
            propose_skill,
        )

        draft = await asyncio.wait_for(
            propose_skill(session_id, deps), timeout=deps.settings.llm_call_timeout_sec
        )
        log.info("post: skill distiller proposed draft %s for session %s", draft.id, session_id)
    except Exception:
        log.exception("post: skill distiller failed for session %s", session_id)


# 按会话串行化当前进程中的评分，避免重复模型费用；此锁不协调多个 API 进程。
_scoring_locks = KeyedLocks()


def _scoring_lock(session_id: str) -> asyncio.Lock:
    return _scoring_locks.get(session_id)


async def run_score(req: ScoreRequest, deps: Deps) -> ScoreCard:
    """串行处理同一会话的评分，完成后复用已保存的成绩单。

    缺少上下文、没有有效回答或能力评估失败时不保存成绩单；
    语言或报告生成失败则保留能力分数，保存降级结果并标记 complete。
    """
    async with _scoring_lock(req.session_id):
        try:
            return await _run_score_locked(req, deps)
        except (Exception, asyncio.CancelledError):
            # 取消或存储失败也需释放 scoring 状态，但已完成的成绩单不能被覆盖。
            try:
                async with session_mutations.get(req.session_id):
                    view = await deps.repo.get_session_view(req.session_id)
                    if view is not None and view.status == "scoring":
                        await deps.repo.update_status(req.session_id, "error")
            except Exception:
                log.exception("post: could not mark scoring failure for %s", req.session_id)
            raise


async def _run_score_locked(req: ScoreRequest, deps: Deps) -> ScoreCard:
    # 锁内再次检查完成状态，让并发请求等待后复用结果。
    async with session_mutations.get(req.session_id):
        view = await deps.repo.get_session_view(req.session_id)
        if view is not None and view.status == "complete" and view.scorecard is not None:
            log.info("post: session %s already scored; returning persisted card", req.session_id)
            return view.scorecard

        ctx = view.context if view is not None else None
        if ctx is None:
            # 无上下文时仅返回空结果，保留准备失败会话的原状态。
            return _missing_context_scorecard(req.session_id)

        # 仅计划中最后一条非空回答可用于评分，未知题号不能制造已完成的零分报告。
        by_question = {a.question_id: a for a in ctx.answers}
        if not any(
            q.id in by_question and by_question[q.id].transcript.strip()
            for q in ctx.plan.questions
        ):
            log.info("post: session %s has no answers; skipping scoring (no_answers)", req.session_id)
            await deps.repo.update_status(req.session_id, "no_answers")
            return _no_answers_scorecard(req.session_id)
        await deps.repo.update_status(req.session_id, "scoring")

    timeout = deps.settings.score_stage_timeout_sec

    with start_trace("score", session_id=req.session_id):
        with start_span("post.evaluate"):
            comp_scores = await _guarded(evaluate(ctx, deps), label="evaluate", timeout=timeout)
        if comp_scores is None:
            # 整体能力评估失败不能视为零分；保留上下文并标记 error，允许重试。
            log.error("post: evaluate stage failed for %s; marking error (no card persisted)", req.session_id)
            await deps.repo.update_status(req.session_id, "error")
            return _degraded_scorecard(ctx, [], _fallback_language_report())

        # 校准失败时沿用原分数，避免可选验证阶段使评分失效。
        if deps.settings.enable_score_verifier:
            with start_span("post.verify"):
                verified = await _guarded(
                    verify_scores(ctx, comp_scores, deps), label="verify", timeout=timeout
                )
            if verified is not None:
                comp_scores = verified

        with start_span("post.coach"):
            lang_report = await _guarded(coach(ctx, deps), label="coach", timeout=timeout)
        if lang_report is None:
            lang_report = _fallback_language_report()

        with start_span("post.report"):
            scorecard = await _guarded(
                generate_report(ctx, comp_scores, lang_report, deps),
                label="generate_report",
                timeout=timeout,
            )
        if scorecard is None:
            scorecard = _degraded_scorecard(ctx, comp_scores, lang_report)

        async with session_mutations.get(req.session_id):
            await deps.repo.complete_session(req.session_id, scorecard)
        add_event(
            "score.complete",
            {"overall": scorecard.overall_score, "competencies": len(scorecard.competency_scores)},
        )

        await _maybe_distill_skill(req.session_id, deps)

        return scorecard
