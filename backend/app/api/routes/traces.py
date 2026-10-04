"""只读本地 JSONL 追踪列表和详情；此路由未配置内部密钥校验。

仅显式开启 TRACE_INCLUDE_PROMPTS 时记录提示词预览。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ...core.config import get_settings
from ...core.tracing import list_traces, read_trace

router = APIRouter()


class TraceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    traces: list[dict] = Field(default_factory=list)


@router.get("/api/traces", response_model=TraceListResponse)
def get_traces(
    session_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> TraceListResponse:
    directory = Path(get_settings().trace_dir)
    return TraceListResponse(
        traces=list_traces(directory=directory, session_id=session_id, limit=limit)
    )


@router.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    detail = read_trace(trace_id, directory=Path(get_settings().trace_dir))
    if detail is None:
        raise HTTPException(status_code=404, detail="Unknown trace_id")
    return detail
