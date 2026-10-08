"""根据评分卡生成学习计划，并通过知识检索回答学习问题。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from ...dependencies.container import build_deps
from ...schemas.shared_models import CoachChatRequest, CoachReply, ScoreCard, StudyPlan
from ...services.coach.pipeline import run_coach_chat, run_coach_plan

router = APIRouter()
_MAX_QUERY_LEN = 10_000
_MAX_PLAN_COMPETENCIES = 100


class CoachPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scorecard: ScoreCard


@router.post("/api/coach/plan", response_model=StudyPlan)
async def coach_plan(req: CoachPlanRequest) -> StudyPlan:
    if len(req.scorecard.weak_competencies) > _MAX_PLAN_COMPETENCIES:
        raise HTTPException(status_code=413, detail="Too many study competencies")
    return await run_coach_plan(req.scorecard, build_deps())


@router.post("/api/coach/chat", response_model=CoachReply)
async def coach_chat(req: CoachChatRequest) -> CoachReply:
    if len(req.query) > _MAX_QUERY_LEN:
        raise HTTPException(status_code=413, detail="Query too large")
    return await run_coach_chat(req, build_deps())
