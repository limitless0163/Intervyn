"""模型、联网研究和嵌入的可替换接口。"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from ...schemas.shared_models import Citation

T = TypeVar("T", bound=BaseModel)


class GroundedResearch(BaseModel):
    text: str
    sources: list[Citation]
    search_suggestions: str | None = None


@runtime_checkable
class LLMAdapter(Protocol):
    """生成文本或经指定 Pydantic 模型校验的结构化结果。"""

    async def complete_text(self, *, system: str, user: str) -> str: ...

    async def complete_json(self, *, system: str, user: str, schema: type[T]) -> T: ...


@runtime_checkable
class ResearchAdapter(Protocol):
    """由模型执行联网研究，返回正文和实际搜索来源。"""

    async def research(self, *, system: str, user: str) -> GroundedResearch: ...


@runtime_checkable
class EmbeddingsAdapter(Protocol):
    """为文本列表生成对应的嵌入向量。"""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
