"""创建 prep 状态的会话后在后台执行准备流程，客户端通过会话接口轮询进度。

Starlette TestClient 会等待后台任务完成后才返回响应。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ...dependencies.container import build_deps
from ...schemas.shared_models import PrepRequest, PrepResponse
from ...services.prep import run_prep_for_session

router = APIRouter()

# 在路由层限制字符数，避免影响共享契约的 TS/Pydantic 一致性。
# cv_url 可承载粘贴文本或文件 data URL，因此预留较大额度。
_MAX_CV_URL_LEN = 2_000_000  # 包含编码后文件内容的字符数上限。
_MAX_JD_LEN = 200_000
_MAX_COMPANY_LEN = 500


@router.post("/api/prep", response_model=PrepResponse)
async def prep(req: PrepRequest, background_tasks: BackgroundTasks) -> PrepResponse:
    if (
        len(req.cv_url) > _MAX_CV_URL_LEN
        or len(req.jd_text) > _MAX_JD_LEN
        or len(req.company) > _MAX_COMPANY_LEN
    ):
        raise HTTPException(status_code=413, detail="CV/JD/company input too large")
    deps = build_deps()
    session_id = await deps.repo.create_session(req)
    background_tasks.add_task(run_prep_for_session, session_id, req, deps)
    return PrepResponse(session_id=session_id)
