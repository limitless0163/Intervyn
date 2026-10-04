"""仅评估有正文的回答；能力标识由问题固定，等级由数值推导。

同一能力的多题分数取平均；未答题不作为零分，单题失败不丢弃其他评分。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ...schemas.shared_models import CompetencyScore, MasteryLevel
from .prompts import evaluate_answer_prompts

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import AnswerRecord, InterviewContext, PlannedQuestion

log = get_logger(__name__)

# 限制并发量，以兼顾长面试的阶段时限和提供方请求额度。
_MAX_CONCURRENT_SCORING = 4


def _clamp_score(value: float) -> float:
    """将模型分数限制在 0 至 5 的约定范围。"""
    return max(0.0, min(5.0, float(value)))


def level_for_score(score: float) -> MasteryLevel:
    """按分数推导等级：4 起为 strong，3 起为 solid，2 起为 developing，其余为 weak。"""
    if score >= 4.0:
        return "strong"
    if score >= 3.0:
        return "solid"
    if score >= 2.0:
        return "developing"
    return "weak"


def _answers_by_question(ctx: InterviewContext) -> dict[str, AnswerRecord]:
    """按问题 ID 索引回答；重复 ID 使用最后一条记录。"""
    return {a.question_id: a for a in ctx.answers}


async def _score_question(
    question: PlannedQuestion,
    answer: AnswerRecord,
    deps: Deps,
) -> CompetencyScore:
    """依据评分标准评估已作答问题，强制使用计划中的能力标识并按数值推导等级。"""
    system, user = evaluate_answer_prompts(question, answer.transcript)
    raw = await deps.llm.complete_json(system=system, user=user, schema=CompetencyScore)

    score = _clamp_score(raw.score)
    evidence = raw.evidence or "Scored against the question rubric."

    return CompetencyScore(
        competency=question.target_competency,
        score=score,
        evidence=evidence,
        level=level_for_score(score),
    )


def _merge_by_competency(scores: list[CompetencyScore]) -> list[CompetencyScore]:
    """按能力合并平均分并重新推导等级，保留能力首次出现的顺序。"""
    order: list[str] = []
    buckets: dict[str, list[CompetencyScore]] = {}
    for cs in scores:
        if cs.competency not in buckets:
            buckets[cs.competency] = []
            order.append(cs.competency)
        buckets[cs.competency].append(cs)

    merged: list[CompetencyScore] = []
    for competency in order:
        group = buckets[competency]
        if len(group) == 1:
            merged.append(group[0])
            continue
        avg = _clamp_score(sum(cs.score for cs in group) / len(group))
        evidence = " ".join(cs.evidence for cs in group if cs.evidence).strip()
        merged.append(
            CompetencyScore(
                competency=competency,
                score=avg,
                evidence=evidence or "Averaged across multiple questions.",
                level=level_for_score(avg),
            )
        )
    return merged


async def evaluate(ctx: InterviewContext, deps: Deps) -> list[CompetencyScore]:
    """有界并发评估已回答的问题，再按能力合并分数。

    未答题跳过，覆盖率单独报告；单题失败只丢弃该题，全部调用失败则抛出阶段异常。
    """
    by_question = _answers_by_question(ctx)
    answered = [
        (question, by_question[question.id])
        for question in ctx.plan.questions
        if question.id in by_question
        and (by_question[question.id].transcript or "").strip()
    ]

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SCORING)

    async def _score_one(question: PlannedQuestion, answer: AnswerRecord) -> CompetencyScore | None:
        async with semaphore:
            try:
                return await _score_question(question, answer, deps)
            except Exception:
                log.exception("evaluator: scoring failed for question %s; skipping", question.id)
                return None

    results = await asyncio.gather(*(_score_one(q, a) for q, a in answered))
    raw_scores = [r for r in results if r is not None]
    if answered and not raw_scores:
        # 所有题目调用失败属于阶段失败，不能保存成已完成的零分报告。
        raise RuntimeError("evaluator: all per-question scoring calls failed")
    return _merge_by_competency(raw_scores)
