"""知识侧车的 HTTP 接口；原始文本可直接入库，URL 仅在成功读取时入库。

被拒绝或读取失败的 URL 返回空正文并跳过入库，不把 URL 本身当作资料。
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import os
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

from .backend import get_backend
from .models import (
    KbIngestRequest,
    KbIngestResponse,
    KbQueryRequest,
    KbQueryResponse,
)

if TYPE_CHECKING:
    from .backend import RagBackend

# 文件 URL 的读取时限，单位为秒。
_FETCH_TIMEOUT = 15.0
_MAX_INGEST_FILES = 100
_MAX_INGEST_TOTAL_LEN = 5_000_000
_MAX_DOCUMENT_BYTES = 1_000_000
_MAX_QUERY_LEN = 10_000
_FETCH_CONCURRENCY = 4


def _is_public_http_url(url: str) -> bool:
    """校验协议、主机名与 IP 字面量，拒绝本地或私有目标。

    不解析 DNS，不能阻止域名解析到内网；部署时仍需限制网络出口。
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if parts.username is not None or parts.password is not None:
        return False
    host = (parts.hostname or "").strip("[]").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith((".localhost", ".internal")):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return True  # 普通域名不解析 DNS，防护边界见函数说明。
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


async def require_secret(
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """配置 LIGHTRAG_API_SECRET 时校验内部密钥，未配置时跳过。"""
    expected = os.environ.get("LIGHTRAG_API_SECRET")
    if not expected:
        return
    if not x_internal_secret or not hmac.compare_digest(
        x_internal_secret.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing internal secret")


async def _resolve_file(ref: str, client: httpx.AsyncClient | None = None) -> tuple[str, str]:
    """将文件引用转换为 (source_id, text)。

    非 HTTP(S) 引用按原始文本处理；URL 被拒绝或读取失败时保留来源并返回空正文。
    """
    is_url = ref.lower().startswith(("http://", "https://"))
    if is_url:
        if not _is_public_http_url(ref):
            # 拒绝目标不尝试联网，也不将地址本身作为正文。
            return (ref, "")
        try:
            if client is None:
                async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as owned_client:
                    return await _resolve_file(ref, owned_client)
            # 总时限包含所有读取；禁止重定向，并在解压后的字节流上限制大小。
            async with asyncio.timeout(_FETCH_TIMEOUT):
                async with client.stream("GET", ref, follow_redirects=False) as resp:
                    resp.raise_for_status()
                    length = resp.headers.get("content-length")
                    if length and int(length) > _MAX_DOCUMENT_BYTES:
                        return (ref, "")
                    content = bytearray()
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        content.extend(chunk)
                        if len(content) > _MAX_DOCUMENT_BYTES:
                            return (ref, "")
                    return (ref, content.decode(resp.encoding or "utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 - 读取失败时跳过该来源
            return (ref, "")
    # 文本首行作为稳定来源标签，正文保留完整内容。
    label = ref.strip().split("\n", 1)[0][:60] or "text"
    return (label, ref)


def create_app(backend: RagBackend | None = None) -> FastAPI:
    """构造知识 API；可注入检索后端，未注入时按环境配置选择。"""
    backend = backend or get_backend()
    app = FastAPI(title="Intervyn Knowledge Sidecar", version="0.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "backend": os.environ.get("RAG_BACKEND", "naive")}

    @app.post(
        "/kb/ingest",
        response_model=KbIngestResponse,
        dependencies=[Depends(require_secret)],
    )
    async def kb_ingest(req: KbIngestRequest) -> KbIngestResponse:
        if len(req.files) > _MAX_INGEST_FILES or (
            sum(len(ref) for ref in req.files) > _MAX_INGEST_TOTAL_LEN
        ):
            raise HTTPException(status_code=413, detail="Ingest payload too large")
        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            async def resolve(ref: str) -> tuple[str, str]:
                async with semaphore:
                    return await _resolve_file(ref, client)

            resolved = await asyncio.gather(*(resolve(ref) for ref in req.files))
        docs = [(source_id, text) for source_id, text in resolved if text]
        if sum(len(text) for _, text in docs) > _MAX_INGEST_TOTAL_LEN:
            raise HTTPException(status_code=413, detail="Resolved documents too large")
        track_id = await backend.ingest(req.user_id, docs)
        return KbIngestResponse(track_id=track_id)

    @app.post(
        "/kb/query",
        response_model=KbQueryResponse,
        dependencies=[Depends(require_secret)],
    )
    async def kb_query(req: KbQueryRequest) -> KbQueryResponse:
        if len(req.query) > _MAX_QUERY_LEN:
            raise HTTPException(status_code=413, detail="Query too large")
        answer, citations = await backend.query(req.user_id, req.query, req.lang)
        return KbQueryResponse(answer=answer, citations=citations)

    return app


app = create_app()


def main() -> None:
    """使用 LIGHTRAG_PORT 指定端口运行 uvicorn，默认端口为 9621。"""
    import uvicorn

    port = int(os.environ.get("LIGHTRAG_PORT", "9621"))
    uvicorn.run(
        "lightrag_service.app:app",
        host="0.0.0.0",
        port=port,
    )


if __name__ == "__main__":
    main()
