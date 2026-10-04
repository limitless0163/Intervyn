"""离线验证知识客户端及工厂选择；不导入 LiveKit 或连接侧车。"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.core.adapters.knowledge import (
    HttpKnowledge,
    KnowledgeClient,
    MockKnowledge,
    get_knowledge,
)
from app.core.config import Settings
from app.schemas.shared_models import Citation


@pytest.fixture(autouse=True)
def _no_local_dotenv(monkeypatch, tmp_path):
    """隔离工作目录和环境中的侧车地址，避免默认工厂测试选中 HTTP 客户端。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIGHTRAG_URL", raising=False)


def _run(coro):
    return asyncio.run(coro)


def test_mock_knowledge_returns_answer_and_shared_citations() -> None:
    answer, citations = _run(MockKnowledge().search("u1", "system design", "en"))
    assert isinstance(answer, str) and answer
    assert "system design" in answer
    assert len(citations) == 2
    assert all(isinstance(c, Citation) for c in citations)


def test_mock_knowledge_is_deterministic() -> None:
    a = _run(MockKnowledge().search("u1", "graphs", "en"))
    b = _run(MockKnowledge().search("u1", "graphs", "en"))
    assert a[0] == b[0]
    assert [c.model_dump() for c in a[1]] == [c.model_dump() for c in b[1]]


def test_mock_knowledge_satisfies_protocol() -> None:
    assert isinstance(MockKnowledge(), KnowledgeClient)
    assert isinstance(HttpKnowledge("http://localhost:9621"), KnowledgeClient)


def test_get_knowledge_returns_mock_without_lightrag_url(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTRAG_URL", raising=False)
    client = get_knowledge(Settings())
    assert isinstance(client, MockKnowledge)
    answer, citations = _run(client.search("u1", "behavioral", "en"))
    assert isinstance(answer, str)
    assert all(isinstance(c, Citation) for c in citations)


def test_get_knowledge_returns_http_with_lightrag_url(monkeypatch) -> None:
    monkeypatch.setenv("LIGHTRAG_URL", "http://lightrag:9621")
    client = get_knowledge(Settings())
    assert isinstance(client, HttpKnowledge)


def test_mock_knowledge_ingest_returns_deterministic_stub() -> None:
    track = _run(MockKnowledge().ingest("sess_abc", ["doc one", "doc two"]))
    assert track == "trk-sess_abc-2"
    # 固定输入应返回稳定标识，不使用随机 UUID 或进程相关哈希。
    assert track == _run(MockKnowledge().ingest("sess_abc", ["doc one", "doc two"]))


def test_http_ingest_validates_upstream_contract_instead_of_inventing_ack(monkeypatch):
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"unexpected": "value"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    with pytest.raises(ValidationError):
        _run(HttpKnowledge("http://sidecar").ingest("u", ["notes"]))
