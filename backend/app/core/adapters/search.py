"""按配置选择搜索适配器；配置不足时使用离线模拟，SDK 延迟导入。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..logging import get_logger
from .base import SearchAdapter, SearchResult
from .mock import MockSearch

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger(__name__)


class TavilySearch:
    """通过延迟导入的 tavily-python SDK 搜索网页。"""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _client(self) -> Any:
        try:
            from tavily import TavilyClient
        except ImportError as exc:  # pragma: no cover - 依赖可选 SDK
            raise RuntimeError(
                "tavily-python is not installed; install the 'tavily' extra."
            ) from exc
        return TavilyClient(api_key=self._api_key)

    async def search(
        self, query: str, *, lang: str = "en", max_results: int = 6
    ) -> list[SearchResult]:
        import asyncio

        client = self._client()

        def _run() -> dict[str, Any]:
            return client.search(query=query, max_results=max_results)

        data = await asyncio.to_thread(_run)
        results: list[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                )
            )
        return results


def get_search(settings: Settings) -> SearchAdapter:
    """按提供方和密钥选择搜索适配器，配置不足时回退到模拟实现。"""
    provider = (settings.search_provider or "mock").lower()
    if provider == "mock":
        return MockSearch()
    if provider == "tavily":
        if settings.tavily_api_key:
            return TavilySearch(settings.tavily_api_key)
        log.warning("search_provider=tavily but tavily_api_key is missing; using MockSearch.")
        return MockSearch()
    log.warning("Unknown search_provider=%r; using MockSearch.", provider)
    return MockSearch()
