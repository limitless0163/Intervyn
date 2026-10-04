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

router = APIRouter()


class LiveResultRequest(BaseModel):
    """内部 Python 回写载荷，不纳入 TypeScript 与 Pydantic 的共享契约注册表。"""

    model_config = ConfigDict(extra="forbid")
    context: InterviewContext
    transcript: list[dict] = Field(default_factory=list)
    # 仅接受白名单终态，避免工作进程任意改写评分状态。
    status: str | None = None


_ALLOWED_LIVE_STATUSES = {"no_answers", "error"}

# 终态之后拒绝迟到的检查点或重放写入，避免覆盖已完成的面试记录。
_TERMINAL_STATUSES = {"complete", "no_answers", "error", "rejected"}


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
    deps = build_deps()
    view = await deps.repo.get_session_view(session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if req.context.session_id != session_id:
        raise HTTPException(status_code=422, detail="Context session_id must match the URL")
    if view.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409, detail=f"Session already {view.status}"
        )
    if req.transcript:
        await deps.repo.save_transcript(session_id, req.transcript)
    await deps.repo.save_context(session_id, req.context)
    if req.status in _ALLOWED_LIVE_STATUSES:
        await deps.repo.update_status(session_id, req.status)
    return {"ok": True}
