"""可选复核 weak/developing 分数；默认关闭，失败时保留原评分。

输出保留能力数量和顺序，修正分数限制在 0 至 5，并据此重新推导等级。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...core.logging import get_logger
from ...schemas.shared_models import CompetencyScore
from .evaluator import level_for_score
from .prompts import verify_score_prompts

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import InterviewContext

log = get_logger(__name__)

__all__ = ["verify_scores"]

# 仅复核 weak/developing 等级，高分保持不变。
_VERIFY_LEVELS = frozenset({"weak", "developing"})


class _Verdict(BaseModel):
    """模型给出单项复核结论；能力标识与等级仍由代码约束。"""

    model_config = ConfigDict(extra="forbid")
    justified: bool
    adjusted_score: float
    reason: str


def _clamp_score(value: float) -> float:
    """将修正分数限制在 0 至 5 的约定范围。"""
    return max(0.0, min(5.0, float(value)))


async def _guarded(coro, *, label: str, timeout: float):
    """限时等待复核；异常时返回 None，供调用方保留原分数。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        log.exception("verifier: check %r failed; keeping original score", label)
        return None


async def verify_scores(
    ctx: InterviewContext,
    comp_scores: list[CompetencyScore],
    deps: Deps,
) -> list[CompetencyScore]:
    """逐项复核低分，保持能力数量和顺序；高分、认可原分数或复核失败时保留原对象。

    需要修正时限制新分数范围并重新推导等级。
    """
    semaphore = asyncio.Semaphore(4)
    count = sum(cs.level in _VERIFY_LEVELS for cs in comp_scores)
    waves = max(1, (count + 3) // 4)
    timeout = min(
        deps.settings.score_verifier_timeout_sec, deps.settings.score_stage_timeout_sec * 0.8 / waves
    )

    # 按目标能力收集实际回答并截断，避免仅审核首轮模型自己生成的证据。
    answers_by_qid = {a.question_id: a for a in ctx.answers}
    transcript_by_competency: dict[str, str] = {}
    for q in ctx.plan.questions:
        a = answers_by_qid.get(q.id)
        if a is None or not (a.transcript or "").strip():
            continue
        prev = transcript_by_competency.get(q.target_competency, "")
        joined = f"{prev}\n\n{a.transcript}".strip()
        transcript_by_competency[q.target_competency] = joined[:4000]

    async def verify_one(cs: CompetencyScore) -> CompetencyScore:
        if cs.level not in _VERIFY_LEVELS:
            return cs

        system, user = verify_score_prompts(
            cs.competency,
            cs.evidence,
            cs.score,
            transcript_excerpt=transcript_by_competency.get(cs.competency, ""),
        )
        async with semaphore:
            verdict = await _guarded(
                deps.llm.complete_json(system=system, user=user, schema=_Verdict),
                label=f"score:{cs.competency}", timeout=timeout,
            )
        if verdict is None or verdict.justified:
            return cs

        adjusted = _clamp_score(verdict.adjusted_score)
        return CompetencyScore(
            competency=cs.competency,
            score=adjusted,
            evidence=cs.evidence,
            level=level_for_score(adjusted),
        )
    return list(await asyncio.gather(*(verify_one(cs) for cs in comp_scores)))
