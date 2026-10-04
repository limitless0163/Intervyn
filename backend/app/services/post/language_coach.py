"""依据回答文本评估表达流畅度和清晰度等语言指标，并限制数值范围。

此阶段只读取转写文本，不直接分析原始音频。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...schemas.shared_models import LanguageReport
from .prompts import language_coach_prompts

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import InterviewContext


def _transcript(ctx: InterviewContext) -> str:
    """合并候选人的回答正文，供语言评估统一读取。"""
    parts = [a.transcript.strip() for a in ctx.answers if a.transcript and a.transcript.strip()]
    return "\n\n".join(parts)


def _clamp_score(value: float) -> float:
    return max(0.0, min(5.0, float(value)))


async def coach(ctx: InterviewContext, deps: Deps) -> LanguageReport:
    """生成语言报告；分数限制为 0 至 5，填充词数量不得为负。"""
    transcript = _transcript(ctx)
    primary = ctx.plan.language_mode.primary
    system, user = language_coach_prompts(transcript, primary)
    report = await deps.llm.complete_json(system=system, user=user, schema=LanguageReport)

    return report.model_copy(
        update={
            "fluency_score": _clamp_score(report.fluency_score),
            "clarity_score": _clamp_score(report.clarity_score),
            "filler_word_count": max(0, int(report.filler_word_count)),
        }
    )
