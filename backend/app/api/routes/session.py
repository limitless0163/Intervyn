"""会话读取与语音工作进程的结果回写入口。

工作进程必须通过 API 回写，才能在默认内存存储模式下写入 API 所属的仓库。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ...dependencies.auth import require_internal_secret
from ...dependencies.container import build_deps
from ...schemas.shared_models import InterviewContext
from ...schemas.views import SessionView
from ...services.session import (
    SessionConflictError,
    SessionIdentityError,
    SessionNotFoundError,
    save_live_result,
)

router = APIRouter()


class LiveResultRequest(BaseModel):
    """内部 Python 回写载荷，不纳入 TypeScript 与 Pydantic 的共享契约注册表。"""

    model_config = ConfigDict(extra="forbid")
    context: InterviewContext
    transcript: list[dict] = Field(default_factory=list)
    # 仅接受白名单终态，避免工作进程任意改写评分状态。
    status: str | None = None


class CoachTranscriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: list[dict] = Field(default_factory=list, max_length=1000)


@router.get("/api/session/{session_id}", response_model=SessionView)
async def get_session(session_id: str) -> SessionView:
    view = await build_deps().repo.get_session_view(session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return view


@router.post(
    "/api/session/{session_id}/live-result",
    dependencies=[Depends(require_internal_secret)],
)
async def post_live_result(session_id: str, req: LiveResultRequest) -> dict:
    """先核对会话身份与终态，再回写转录和上下文；只采纳允许的终态提示。"""
    deps = build_deps()
    try:
        await save_live_result(
            session_id, req.context, req.transcript, req.status, deps.repo
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SessionIdentityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}


@router.post(
    "/api/session/{session_id}/coach-transcript",
    dependencies=[Depends(require_internal_secret)],
)
async def post_coach_transcript(session_id: str, req: CoachTranscriptRequest) -> dict:
    """教练工作进程也通过 API 回写，支持默认内存模式并保持两种转录分离。"""
    repo = build_deps().repo
    if await repo.get_session_view(session_id) is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    await repo.save_coach_transcript(session_id, req.transcript)
    return {"ok": True}
