"""离线验证 NaiveRAG 分块、来源引用及用户隔离，不依赖模型或真实网络。"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from lightrag_service import app as app_module
from lightrag_service.app import create_app
from lightrag_service.backend import NaiveRAG, get_backend
from lightrag_service.models import Citation


def _run(coro):
    return asyncio.run(coro)


def test_query_returns_relevant_chunk_and_citation() -> None:
    backend = NaiveRAG()
    _run(
        backend.ingest(
            "user-a",
            [
                ("cv.txt", "Jane built a payments platform handling 2M transactions."),
                ("notes.txt", "The candidate enjoys hiking and photography on weekends."),
            ],
        )
    )
    answer, citations = _run(backend.query("user-a", "payments platform", "en"))

    assert "payments" in answer.lower()
    assert len(citations) >= 1
    assert all(isinstance(c, Citation) for c in citations)
    assert citations[0].title == "cv.txt"
    assert citations[0].url == "cv.txt"
    assert "payments" in (citations[0].snippet or "").lower()


def test_per_user_isolation() -> None:
    backend = NaiveRAG()
    _run(backend.ingest("alice", [("a.txt", "Alice specialises in distributed systems.")]))
    _run(backend.ingest("bob", [("b.txt", "Bob specialises in mobile development.")]))

    # 用户之间不得检索到对方的资料。
    answer, citations = _run(backend.query("bob", "distributed systems", "en"))
    assert "alice" not in answer.lower()
    assert all(c.title != "a.txt" for c in citations)

    a_answer, a_citations = _run(backend.query("alice", "distributed systems", "en"))
    assert "distributed" in a_answer.lower()
    assert any(c.title == "a.txt" for c in a_citations)


def test_query_is_deterministic() -> None:
    def build_and_query() -> tuple[str, list[dict]]:
        backend = NaiveRAG()
        _run(
            backend.ingest(
                "u",
                [
                    ("doc1", "Kubernetes orchestrates containers across a cluster."),
                    ("doc2", "Docker packages an application into a container image."),
                    ("doc3", "Containers share the host kernel and start fast."),
                ],
            )
        )
        ans, cites = _run(backend.query("u", "container container kernel", "en"))
        return ans, [c.model_dump() for c in cites]

    a = build_and_query()
    b = build_and_query()
    assert a == b


def test_empty_or_unmatched_query_returns_empty() -> None:
    backend = NaiveRAG()
    _run(backend.ingest("u", [("d.txt", "Some unrelated content about cooking.")]))
    answer, citations = _run(backend.query("u", "quantum chromodynamics", "en"))
    assert answer == ""
    assert citations == []

    # 未知用户必须返回空结果，不能泄漏已有资料。
    answer2, citations2 = _run(backend.query("nobody", "cooking", "en"))
    assert answer2 == ""
    assert citations2 == []


def test_get_backend_defaults_to_naive(monkeypatch) -> None:
    monkeypatch.delenv("RAG_BACKEND", raising=False)
    assert isinstance(get_backend(), NaiveRAG)
    monkeypatch.setenv("RAG_BACKEND", "naive")
    assert isinstance(get_backend(), NaiveRAG)


def test_app_exposes_kb_routes() -> None:
    app = create_app(backend=NaiveRAG())
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/kb/ingest" in paths
    assert "/kb/query" in paths


@pytest.mark.parametrize("text,query,lang", [
    ("候选人负责支付平台的幂等设计和故障恢复", "支付平台", "zh"),
    ("候補者は分散システムの運用を担当しました", "分散システム", "ja"),
    ("Équipe spécialisée en résilience distribuée", "résilience", "fr"),
])
def test_unicode_materials_are_retrievable(text, query, lang):
    backend = NaiveRAG()
    _run(backend.ingest("owner", [("notes", text)]))
    answer, citations = _run(backend.query("owner", query, lang))
    assert answer == text
    assert citations[0].title == "notes"


@pytest.mark.parametrize("url", ["http://localhost./notes", "http://a.localhost./notes", "https://user:pass@example.com/notes"])
def test_unsafe_source_urls_are_rejected(url):
    assert not app_module._is_public_http_url(url)


def test_unicode_sidecar_secret_mismatch_returns_401(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_API_SECRET", "key")
    with pytest.raises(HTTPException) as error:
        _run(app_module.require_secret("错误"))
    assert error.value.status_code == 401


@pytest.mark.parametrize("declared_size", [True, False])
def test_remote_source_size_limit_handles_headers_and_streams(monkeypatch, declared_size):
    monkeypatch.setattr(app_module, "_MAX_DOCUMENT_BYTES", 10)
    headers = {"content-length": "1000"} if declared_size else {}

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 20

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers=headers, stream=Stream())
        )) as client:
            return await app_module._resolve_file("https://example.com/notes", client)

    assert _run(exercise()) == ("https://example.com/notes", "")


def test_sidecar_never_follows_redirects():
    seen = []

    def respond(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await app_module._resolve_file("https://example.com/notes", client)

    assert _run(exercise()) == ("https://example.com/notes", "")
    assert seen == ["https://example.com/notes"]


def test_direct_sidecar_api_enforces_payload_limits_before_ingestion(monkeypatch):
    monkeypatch.delenv("LIGHTRAG_API_SECRET", raising=False)
    monkeypatch.setattr(app_module, "_MAX_INGEST_FILES", 1)
    monkeypatch.setattr(app_module, "_MAX_QUERY_LEN", 5)
    backend = NaiveRAG()
    with TestClient(create_app(backend)) as client:
        response = client.post("/kb/ingest", json={"user_id": "u", "files": ["one", "two"]})
        assert response.status_code == 413
        assert backend._stores == {}
        assert client.post("/kb/query", json={"user_id": "u", "query": "long query", "lang": "en"}).status_code == 413


def test_ingest_has_bounded_concurrency_and_preserves_source_order(monkeypatch):
    monkeypatch.delenv("LIGHTRAG_API_SECRET", raising=False)
    active = peak = 0

    async def resolve(ref, client):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return ref, "payments " + ref

    monkeypatch.setattr(app_module, "_resolve_file", resolve)
    backend = NaiveRAG()
    with TestClient(create_app(backend)) as client:
        response = client.post("/kb/ingest", json={"user_id": "u", "files": [str(i) for i in range(10)]})
        assert response.status_code == 200
    assert peak == 4
    assert [chunk.source_id for chunk in backend._stores["u"]] == [str(i) for i in range(10)]


def test_resolved_payload_overflow_does_not_partially_ingest(monkeypatch):
    monkeypatch.delenv("LIGHTRAG_API_SECRET", raising=False)
    monkeypatch.setattr(app_module, "_MAX_INGEST_TOTAL_LEN", 5)

    async def resolve(ref, client):
        return ref, "abcdef"

    monkeypatch.setattr(app_module, "_resolve_file", resolve)
    backend = NaiveRAG()
    with TestClient(create_app(backend)) as client:
        assert client.post("/kb/ingest", json={"user_id": "u", "files": ["a"]}).status_code == 413
    assert backend._stores == {}


def test_resolved_overflow_cancels_pending_downloads_and_returns_without_waiting(monkeypatch):
    monkeypatch.delenv("LIGHTRAG_API_SECRET", raising=False)
    monkeypatch.setattr(app_module, "_MAX_INGEST_TOTAL_LEN", 5)
    cancelled = []

    async def resolve(ref, client):
        if ref == "a":
            await asyncio.sleep(0)  # 让另一条下载先开始。
            return ref, "too large"
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(ref)

    monkeypatch.setattr(app_module, "_resolve_file", resolve)
    backend = NaiveRAG()

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(backend)),
                                     base_url="http://test") as client:
            response = await asyncio.wait_for(client.post(
                "/kb/ingest", json={"user_id": "u", "files": ["a", "b"]},
            ), timeout=1)
            assert response.status_code == 413

    _run(exercise())
    assert cancelled == ["b"]
    assert backend._stores == {}
