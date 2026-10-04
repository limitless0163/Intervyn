"""根据能力分数和语言报告组装评分卡；总分、弱项与覆盖率由代码计算。

仅为有回答的题目生成示范答案，模型负责报告叙述。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...core.logging import get_logger
from ...schemas.shared_models import ModelAnswer, ScoreCard
from .prompts import model_answer_prompts, report_summary_prompts

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import CompetencyScore, InterviewContext, LanguageReport

log = get_logger(__name__)

_WEAK_LEVELS = frozenset({"weak", "developing"})

# 限制示范答案生成的并发量，兼顾阶段时限与提供方请求额度。
_MAX_CONCURRENT_DRAFTS = 4


class _ReportNarrative(BaseModel):
    """模型仅生成报告叙述，数值字段由代码另行计算。"""

    model_config = ConfigDict(extra="forbid")
    strengths: list[str]
    weaknesses: list[str]
    next_steps: list[str]
    summary: str


def _overall_score(comp_scores: list[CompetencyScore]) -> float:
    """计算能力分数均值并限制到 0 至 5；空列表返回 0。"""
    if not comp_scores:
        return 0.0
    mean = sum(cs.score for cs in comp_scores) / len(comp_scores)
    return max(0.0, min(5.0, mean))


def _weak_competencies(comp_scores: list[CompetencyScore]) -> list[str]:
    """提取 weak 或 developing 能力，去重并保留顺序。"""
    seen: set[str] = set()
    weak: list[str] = []
    for cs in comp_scores:
        if cs.level in _WEAK_LEVELS and cs.competency not in seen:
            seen.add(cs.competency)
            weak.append(cs.competency)
    return weak


def _coverage_pct(ctx: InterviewContext) -> float:
    """按非空回答计算计划题目的覆盖率；没有计划题目时按完全覆盖返回 1.0。

    用于区分面试中途结束与已答题表现不足。
    """
    total = len(ctx.plan.questions)
    if total == 0:
        return 1.0
    answered_ids = {a.question_id for a in ctx.answers if a.transcript and a.transcript.strip()}
    answered = sum(1 for q in ctx.plan.questions if q.id in answered_ids)
    return answered / total


def _competency_lines(comp_scores: list[CompetencyScore]) -> str:
    if not comp_scores:
        return "- (no competencies scored)"
    return "\n".join(
        f"- {cs.competency}: {cs.score:.1f}/5 ({cs.level}) — {cs.evidence}" for cs in comp_scores
    )


async def _model_answers(ctx: InterviewContext, deps: Deps) -> list[ModelAnswer]:
    """有界并发生成已作答题目的示范答案；单题失败只跳过该答案。

    跳过未答题，避免无依据生成以及额外模型费用。
    """
    by_question = {a.question_id: a for a in ctx.answers}
    answered = [
        (q, by_question[q.id].transcript)
        for q in ctx.plan.questions
        if q.id in by_question and (by_question[q.id].transcript or "").strip()
    ]

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DRAFTS)
    # 按批次数分配调用时限，避免单个慢请求耗尽整个报告阶段的预算。
    waves = max(1, (len(answered) + _MAX_CONCURRENT_DRAFTS - 1) // _MAX_CONCURRENT_DRAFTS)
    draft_timeout = deps.settings.score_stage_timeout_sec * 0.8 / waves

    async def _draft(question, transcript):
        async with semaphore:
            try:
                system, user = model_answer_prompts(question, ctx.candidate, transcript)
                text = await asyncio.wait_for(
                    deps.llm.complete_text(system=system, user=user), timeout=draft_timeout
                )
                return ModelAnswer(question_id=question.id, answer=text)
            except Exception:
                log.exception("report: model answer failed for question %s; skipping", question.id)
                return None

    results = await asyncio.gather(*(_draft(q, t) for q, t in answered))
    return [r for r in results if r is not None]


async def generate_report(
    ctx: InterviewContext,
    comp_scores: list[CompetencyScore],
    lang_report: LanguageReport,
    deps: Deps,
) -> ScoreCard:
    """组装分数、语言报告、示范答案和模型叙述，返回最终评分卡。"""
    overall = _overall_score(comp_scores)
    weak = _weak_competencies(comp_scores)

    async def narrative_task() -> _ReportNarrative:
        system, user = report_summary_prompts(ctx, _competency_lines(comp_scores), overall)
        try:
            return await asyncio.wait_for(
                deps.llm.complete_json(system=system, user=user, schema=_ReportNarrative),
                timeout=deps.settings.score_stage_timeout_sec * 0.8,
            )
        except Exception:
            log.exception("report: narrative unavailable; preserving scores and model answers")
            return _ReportNarrative(
                strengths=[], weaknesses=[], next_steps=[],
                summary=(
                    "评分已完成，详细文字反馈暂时不可用。"
                    if ctx.plan.language_mode.primary == "zh"
                    else "Scores are ready; detailed written feedback is temporarily unavailable."
                ),
            )

    narrative, model_answers = await asyncio.gather(narrative_task(), _model_answers(ctx, deps))

    return ScoreCard(
        overall_score=overall,
        competency_scores=comp_scores,
        strengths=narrative.strengths,
        weaknesses=narrative.weaknesses,
        weak_competencies=weak,
        model_answers=model_answers,
        next_steps=narrative.next_steps,
        language_report=lang_report,
        summary=narrative.summary,
        coverage_pct=_coverage_pct(ctx),
    )
