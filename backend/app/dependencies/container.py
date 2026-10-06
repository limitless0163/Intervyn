"""集中组装配置、提供方和仓库，业务流程通过 Deps 使用可替换的依赖。"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.adapters.base import EmbeddingsAdapter, LLMAdapter, ResearchAdapter
from ..core.adapters.embeddings import get_embeddings
from ..core.adapters.knowledge import KnowledgeClient, get_knowledge
from ..core.adapters.llm import get_llm
from ..core.adapters.research import get_research
from ..core.config import Settings, get_settings
from ..core.tracing import TracedLLM
from ..repositories.repository import SessionRepository, get_repository


@dataclass
class Deps:
    """供业务流程注入的配置、适配器与仓库集合，便于测试替换。"""
    settings: Settings
    llm: LLMAdapter
    research: ResearchAdapter
    embeddings: EmbeddingsAdapter
    knowledge: KnowledgeClient
    repo: SessionRepository


def _assemble(settings: Settings) -> Deps:
    raw_llm = get_llm(settings)
    provider = (settings.llm_provider or "mock").lower()
    return Deps(
        settings=settings,
        # 统一记录模型调用，包括离线模拟；关闭追踪时仍保留原适配器接口。
        llm=TracedLLM(raw_llm, provider=provider),
        research=get_research(settings),
        embeddings=get_embeddings(settings),
        knowledge=get_knowledge(settings),
        repo=get_repository(settings),
    )


# 跨请求复用适配器和连接池；配置缓存清空后，实例变化会使依赖缓存失效。
_default_deps: Deps | None = None


def build_deps(settings: Settings | None = None) -> Deps:
    """默认依赖按配置实例缓存；显式传入配置时重新组装。"""
    global _default_deps
    if settings is not None:
        return _assemble(settings)
    current = get_settings()
    if _default_deps is None or _default_deps.settings is not current:
        _default_deps = _assemble(current)
    return _default_deps
