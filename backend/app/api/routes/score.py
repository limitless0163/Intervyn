"""同步与后台评分入口；后台排队状态仅用于当前 API 进程内去重。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ...core.logging import get_logger
from ...dependencies.container import build_deps
from ...schemas.shared_models import ScoreRequest, ScoreResponse
from ...services.post import run_score

router = APIRouter()
log = get_logger(__name__)
_scheduled_scores: set[str] = set()


async def _score_in_background(req: ScoreRequest, deps) -> None:
    try:
        await run_score(req, deps)
    except Exception:
        log.exception("background scoring failed for %s", req.session_id)
        await deps.repo.update_status(req.session_id, "error")
    finally:
        _scheduled_scores.discard(req.session_id)


@router.post("/api/score/start", status_code=202)
async def start_score(req: ScoreRequest, background_tasks: BackgroundTasks) -> dict:
    """先接受评分任务，避免语音工作进程在关闭期限内等待完整报告。"""
    deps = build_deps()
    view = await deps.repo.get_session_view(req.session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if view.status == "complete" and view.scorecard is not None:
        return {"session_id": req.session_id, "status": "complete"}
    # 数据库中的 scoring 可能残留于重启后；仅依据本进程的实际任务去重。
    if req.session_id in _scheduled_scores:
        return {"session_id": req.session_id, "status": "scoring"}
    _scheduled_scores.add(req.session_id)
    try:
        await deps.repo.update_status(req.session_id, "scoring")
        background_tasks.add_task(_score_in_background, req, deps)
    except Exception:
        _scheduled_scores.discard(req.session_id)
        raise
    return {"session_id": req.session_id, "status": "scoring"}


@router.post("/api/score", response_model=ScoreResponse)
async def score(req: ScoreRequest) -> ScoreResponse:
    scorecard = await run_score(req, build_deps())
    return ScoreResponse(session_id=req.session_id, scorecard=scorecard)
