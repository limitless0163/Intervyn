"""默认将测试固定到离线模拟栈，避免开发者 .env 中的提供方、存储或追踪配置泄漏。

环境覆盖须在缓存配置首次加载前设置；INTERVYN_TEST_USE_ENV=1 可显式启用集成环境。
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("INTERVYN_TEST_USE_ENV") != "1":
    for _var in (
        "LLM_PROVIDER",
        "STT_PROVIDER",
        "TTS_PROVIDER",
        "SEARCH_PROVIDER",
        "EMBEDDINGS_PROVIDER",
    ):
        os.environ[_var] = "mock"
    # 空字符串覆盖 .env，强制使用内存仓库和模拟知识客户端。
    for _var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LIGHTRAG_URL"):
        os.environ[_var] = ""
    # 默认关闭追踪写盘；追踪测试通过临时目录显式开启，避免污染仓库。
    os.environ["TRACE_ENABLED"] = "0"


@pytest.fixture(autouse=True)
def offline_http(monkeypatch):
    """立即拒绝真实 HTTP 连接，仍允许 MockTransport 和 ASGITransport。

    示例文档 URL 因而确定性进入读取失败分支，不依赖 DNS、远程内容或等待超时。
    """
    if os.environ.get("INTERVYN_TEST_USE_ENV") == "1":
        return
    # 独立的朴素检索测试环境可能未安装 httpx，缺失时跳过拦截。
    try:
        import httpx
    except ImportError:
        return

    def reject_http(self, request):
        raise httpx.ConnectError("Network disabled in offline tests", request=request)

    async def reject_async_http(self, request):
        raise httpx.ConnectError("Network disabled in offline tests", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async_http)
