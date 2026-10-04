"""通过同一知识适配器提供入库和检索；调用超时或失败时返回降级结果。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ...core.logging import get_logger
from ...dependencies.container import build_deps
from ...schemas.shared_models import (
    KbIngestRequest,
    KbIngestResponse,
    KbQueryRequest,
    KbQueryResponse,
)

log = get_logger(__name__)

router = APIRouter()

# 入库涉及解析和嵌入，允许比检索更长的等待时间；单位为秒。
_INGEST_TIMEOUT = 60.0
_QUERY_TIMEOUT = 20.0

# 限制文件数量和字符总量，避免单次请求耗尽内存或压垮侧车。
_MAX_INGEST_FILES = 100
_MAX_INGEST_TOTAL_LEN = 5_000_000  # 字符数上限，并非 UTF-8 字节数。
_MAX_QUERY_LEN = 10_000


async def _guarded(coro, *, label: str, timeout: float):
    """限时等待调用；异常时返回 None，由调用方提供降级结果。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        log.exception("kb: stage %r failed; degrading", label)
        return None


@router.post("/api/kb/ingest", response_model=KbIngestResponse)
async def kb_ingest(req: KbIngestRequest) -> KbIngestResponse:
    # 入库与检索必须使用相同的 store_key 和适配器，才能访问同一知识分区。
    if len(req.files) > _MAX_INGEST_FILES or (
        sum(len(f) for f in req.files) > _MAX_INGEST_TOTAL_LEN
    ):
        raise HTTPException(status_code=413, detail="Ingest payload too large")
    deps = build_deps()
    track_id = await _guarded(
        deps.knowledge.ingest(req.store_key, req.files),
        label="ingest",
        timeout=_INGEST_TIMEOUT,
    )
    if track_id is None:
        raise HTTPException(status_code=503, detail="Knowledge ingestion temporarily unavailable")
    return KbIngestResponse(track_id=track_id)


@router.post("/api/kb/query", response_model=KbQueryResponse)
async def kb_query(req: KbQueryRequest) -> KbQueryResponse:
    if len(req.query) > _MAX_QUERY_LEN:
        raise HTTPException(status_code=413, detail="Query too large")
    deps = build_deps()
    grounded = await _guarded(
        deps.knowledge.search(req.store_key, req.query, req.lang),
        label="knowledge",
        timeout=_QUERY_TIMEOUT,
    )
    if grounded is None:
        return KbQueryResponse(
            answer="I couldn't reach the knowledge base just now — try again in a moment.",
            citations=[],
        )
    answer, citations = grounded
    return KbQueryResponse(answer=answer, citations=list(citations))
