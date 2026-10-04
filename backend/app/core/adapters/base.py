"""模型、搜索和嵌入的可替换接口；默认模拟实现无需网络或提供方 SDK。"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


@runtime_checkable
class LLMAdapter(Protocol):
    """生成文本或经指定 Pydantic 模型校验的结构化结果。"""

    async def complete_text(self, *, system: str, user: str) -> str: ...

    async def complete_json(self, *, system: str, user: str, schema: type[T]) -> T: ...


@runtime_checkable
class SearchAdapter(Protocol):
    """为公司研究提供网页搜索结果。"""

    async def search(
        self, query: str, *, lang: str = "en", max_results: int = 6
    ) -> list[SearchResult]: ...


@runtime_checkable
class EmbeddingsAdapter(Protocol):
    """为文本列表生成对应的嵌入向量。"""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
