"""从评分卡生成学习计划，并结合可选知识检索回答学习问题；各调用独立限时降级。

学习计划直接使用评分卡，无需读取仓库；每项弱能力对应一个学习模块。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...core.logging import get_logger
from ...schemas.shared_models import CoachReply, StudyModule, StudyPlan
from .prompts import coach_chat_prompts, study_module_prompts

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import CoachChatRequest, MasteryState, ScoreCard

log = get_logger(__name__)

__all__ = ["run_coach_chat", "run_coach_plan"]

_DEFAULT_EST_MIN = 25
_STAGE_TIMEOUT = 60.0


class _ModuleDraft(BaseModel):
    """模块标题、理由和时长由模型生成；能力标识与掌握状态由代码固定。"""

    model_config = ConfigDict(extra="forbid")
    title: str
    rationale: str
    est_min: int


class _ChatDraft(BaseModel):
    """模型生成回复正文及关联能力，引用由检索结果提供。"""

    model_config = ConfigDict(extra="forbid")
    answer: str
    follow_ups: list[str]


def _status_for_level(level: str) -> MasteryState:
    """将评分等级映射为学习模块的掌握状态。"""
    return "learning" if level == "developing" else "shaky"


def _clamp_min(value: int) -> int:
    """将预计学习时长限制在 5 至 90 分钟。"""
    return max(5, min(90, int(value)))


async def _guarded(coro, *, label: str, timeout: float = _STAGE_TIMEOUT):
    """限时等待调用；异常时返回 None，由调用方提供降级结果。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        log.exception("coach: stage %r failed; degrading", label)
        return None


def _empty_plan(summary: str) -> StudyPlan:
    return StudyPlan(modules=[], summary=summary, total_min=0)


async def run_coach_plan(scorecard: ScoreCard, deps: Deps) -> StudyPlan:
    """按分数从低到高为弱能力生成模块；能力标识和掌握状态保持与评分卡一致。"""
    weak = list(dict.fromkeys(scorecard.weak_competencies))
    if not weak:
        return _empty_plan(
            "No weak areas from your last interview — nice work. Run another mock to stay sharp."
        )

    score_by_comp = {cs.competency: cs for cs in scorecard.competency_scores}
    # 弱项按低分优先排序，评分卡中找不到的能力排在最后。
    weak.sort(key=lambda c: score_by_comp[c].score if c in score_by_comp else 99.0)

    semaphore = asyncio.Semaphore(4)
    waves = max(1, (len(weak) + 3) // 4)
    module_timeout = min(deps.settings.llm_call_timeout_sec, _STAGE_TIMEOUT * 0.8 / waves)

    async def build_module(i: int, comp: str) -> StudyModule:
        cs = score_by_comp.get(comp)
        evidence = cs.evidence if cs is not None else ""
        level = cs.level if cs is not None else "weak"
        system, user = study_module_prompts(comp, evidence, level)
        async with semaphore:
            draft = await _guarded(
                deps.llm.complete_json(system=system, user=user, schema=_ModuleDraft),
                label=f"module:{comp}", timeout=module_timeout,
            )
        if draft is None:
            draft = _ModuleDraft(
                title=f"Strengthen {comp}",
                rationale="A focus area flagged by your last interview.",
                est_min=_DEFAULT_EST_MIN,
            )
        return StudyModule(
            id=f"m{i}",
            title=draft.title,
            competency=comp,
            status=_status_for_level(level),
            est_min=_clamp_min(draft.est_min),
            rationale=draft.rationale,
        )

    modules = await asyncio.gather(*(build_module(i, comp) for i, comp in enumerate(weak, start=1)))
    total = sum(m.est_min for m in modules)
    plural = "s" if len(modules) != 1 else ""
    summary = f"{len(modules)} focus area{plural} from your last interview, about {total} min."
    return StudyPlan(modules=modules, summary=summary, total_min=total)


async def run_coach_chat(req: CoachChatRequest, deps: Deps) -> CoachReply:
    """配置知识侧车时检索并引用资料；默认离线路径仅生成模型回答，不附模拟引用。"""
    if deps.settings.lightrag_url:
        grounded = await _guarded(
            deps.knowledge.search(req.session_id, req.query, req.lang),
            label="knowledge",
        )
        context, citations = grounded if grounded is not None else ("", [])
    else:
        context, citations = "", []

    system, user = coach_chat_prompts(req.query, context, req.lang)
    draft = await _guarded(
        deps.llm.complete_json(system=system, user=user, schema=_ChatDraft),
        label="chat",
    )
    if draft is None:
        return CoachReply(
            answer="I couldn't put together a coached answer just now — try asking again in a moment.",
            citations=citations,
            follow_ups=[],
        )
    return CoachReply(answer=draft.answer, citations=citations, follow_ups=draft.follow_ups[:3])
