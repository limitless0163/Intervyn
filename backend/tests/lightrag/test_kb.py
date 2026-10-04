"""离线验证 NaiveRAG 分块、来源引用及用户隔离，不依赖模型或真实网络。"""

from __future__ import annotations

import asyncio

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
