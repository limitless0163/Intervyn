"""公司研究使用模型提供方原生搜索工具；无搜索证据时拒绝生成研究结果。

不使用独立搜索服务、不回退到模拟资料。普通模型调用仅用于后续结构化整理。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from ...schemas.shared_models import Citation
from .base import GroundedResearch, ResearchAdapter
from .llm import GeminiLLM, OpenAILLM

if TYPE_CHECKING:
    from ..config import Settings


class ResearchUnavailable(RuntimeError):
    """当前配置无法进行可验证的联网研究。"""

    def __init__(self, message: str, reason: str = "no_sources") -> None:
        super().__init__(message)
        self.reason = reason


def _sources(items: list[dict[str, Any]]) -> list[Citation]:
    """只保留工具元数据中的 HTTP(S) 来源，去重并限制载荷。"""
    sources: dict[str, Citation] = {}
    for item in items:
        url = item.get("url", "")
        if not isinstance(url, str):
            continue
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        sources.setdefault(url, Citation(
            title=str(item.get("title") or parsed.hostname)[:300], url=url,
            snippet=str(item.get("content") or "")[:1500] or None,
        ))
    return list(sources.values())[:20]


def _grounded(text: str, items: list[dict[str, Any]], *, searched: bool,
              suggestions: str | None = None) -> GroundedResearch:
    sources = _sources(items)
    if not searched or not sources or not text.strip():
        raise ResearchUnavailable("No verifiable web search results")
    return GroundedResearch(text=text, sources=sources, search_suggestions=suggestions)


class UnavailableResearch:
    def __init__(self, reason: str = "unsupported_provider") -> None:
        self.reason = reason

    async def research(self, *, system: str, user: str) -> GroundedResearch:
        raise ResearchUnavailable(
            "The configured model provider has no web research capability", self.reason,
        )


class GeminiResearch(GeminiLLM):
    async def research(self, *, system: str, user: str) -> GroundedResearch:
        client = self._client()
        try:
            response = await asyncio.wait_for(client.aio.models.generate_content(
                model=self._model, contents=user,
                config={"system_instruction": system, "tools": [{"google_search": {}}]},
            ), timeout=self._timeout)
            candidates = response.candidates or []
            metadata = candidates[0].grounding_metadata if candidates else None
            items = []
            for chunk in getattr(metadata, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                if web:
                    items.append({"title": web.title, "url": web.uri})
            entry = getattr(metadata, "search_entry_point", None)
            return _grounded(
                response.text or "", items,
                searched=bool(getattr(metadata, "web_search_queries", None)),
                suggestions=getattr(entry, "rendered_content", None),
            )
        finally:
            await client.aio.aclose()
            client.close()


class OpenAIResearch(OpenAILLM):
    async def research(self, *, system: str, user: str) -> GroundedResearch:
        client = self._client()
        try:
            response = await asyncio.wait_for(client.responses.create(
                model=self._model, instructions=system, input=user,
                tools=[{"type": "web_search"}], tool_choice="required",
                include=["web_search_call.action.sources"],
            ), timeout=self._timeout)
            items = []
            searched = False
            for output in response.output:
                if output.type == "web_search_call":
                    searched |= output.status == "completed"
                    for source in getattr(output.action, "sources", None) or []:
                        items.append(source.model_dump())
                elif output.type == "message":
                    for content in output.content:
                        for annotation in getattr(content, "annotations", []):
                            if annotation.type == "url_citation":
                                items.append(annotation.model_dump())
            return _grounded(response.output_text, items, searched=searched)
        finally:
            await client.close()


class MiniMaxResearch:
    """使用 MiniMax Anthropic Messages 的服务端 web_search，无需新增 SDK。"""

    def __init__(self, api_key: str, model: str, base_url: str, timeout_sec: float) -> None:
        self._api_key = api_key
        self._model = model
        self._url = base_url.rstrip("/") + "/anthropic/v1/messages"
        self._timeout = timeout_sec

    async def research(self, *, system: str, user: str) -> GroundedResearch:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, headers={
                "x-api-key": self._api_key, "anthropic-version": "2023-06-01",
            }, json={
                "model": self._model, "max_tokens": 8192, "system": system,
                "messages": [{"role": "user", "content": user}],
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            })
            response.raise_for_status()
            data = response.json()
        if data.get("base_resp", {}).get("status_code", 0) != 0:
            raise ResearchUnavailable("MiniMax web research request failed", "request_failed")
        if data.get("stop_reason") == "max_tokens":
            raise ResearchUnavailable("MiniMax web research was truncated", "invalid_response")
        text, items, searched = [], [], False
        for block in data.get("content", []):
            if block.get("type") == "text":
                text.append(block.get("text", ""))
            elif block.get("type") == "web_search_tool_result":
                results = block.get("content", [])
                if isinstance(results, list):
                    searched = True
                    items.extend(r for r in results if r.get("type") == "web_search_result")
        return _grounded("\n".join(text), items, searched=searched)


def get_research(settings: Settings) -> ResearchAdapter:
    """复用准备模型及其密钥；离线/缺密钥配置明确返回不可用。"""
    provider = settings.llm_provider.lower()
    timeout = settings.company_research_timeout_sec
    if provider == "gemini" and settings.gemini_api_key:
        return GeminiResearch(settings.gemini_api_key, settings.gemini_model, timeout)
    if provider == "openai" and settings.openai_api_key:
        return OpenAIResearch(settings.openai_api_key, settings.openai_model, timeout)
    if provider == "minimax" and settings.minimax_api_key:
        return MiniMaxResearch(
            settings.minimax_api_key, settings.minimax_model, settings.minimax_base_url, timeout,
        )
    return UnavailableResearch(
        "not_configured" if provider in {"gemini", "openai", "minimax"}
        else "unsupported_provider",
    )
