"""按配置选择嵌入适配器；未配置提供方或缺少密钥时使用离线模拟实现。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..logging import get_logger
from .base import EmbeddingsAdapter
from .mock import MockEmbeddings

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger(__name__)


class OpenAIEmbeddings:
    """通过延迟导入的 OpenAI SDK 生成嵌入。"""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _client(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - 依赖可选 SDK
            raise RuntimeError(
                "openai is not installed; install the 'openai' extra."
            ) from exc
        return AsyncOpenAI(api_key=self._api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._client()
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in resp.data]


def get_embeddings(settings: Settings) -> EmbeddingsAdapter:
    """按提供方及密钥配置选择适配器，配置不足时回退到模拟实现。"""
    provider = (settings.embeddings_provider or "mock").lower()
    if provider == "mock":
        return MockEmbeddings()
    if provider == "openai":
        if settings.openai_api_key:
            return OpenAIEmbeddings(settings.openai_api_key)
        log.warning(
            "embeddings_provider=openai but openai_api_key is missing; using MockEmbeddings."
        )
        return MockEmbeddings()
    log.warning("Unknown embeddings_provider=%r; using MockEmbeddings.", provider)
    return MockEmbeddings()
