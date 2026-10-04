"""集中注册路由及可选内部密钥校验。"""

from fastapi import APIRouter, Depends

from ..dependencies.auth import require_internal_secret
from .routes import coach, kb, prep, score, session, traces

router = APIRouter()

# 准备、评分、教练和知识接口统一校验内部密钥；会话写入在路由内单独校验。
guarded = [Depends(require_internal_secret)]
router.include_router(prep.router, dependencies=guarded)
router.include_router(score.router, dependencies=guarded)
router.include_router(coach.router, dependencies=guarded)
router.include_router(kb.router, dependencies=guarded)
router.include_router(session.router)
router.include_router(traces.router)
