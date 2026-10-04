"""通过真实侧车 HTTP 路由验证入库、带引用检索、分区隔离和拒绝写入。"""

import pytest
from fastapi.testclient import TestClient

from lightrag_service.app import create_app
from lightrag_service.backend import NaiveRAG


@pytest.fixture
def client():
    with TestClient(create_app(NaiveRAG())) as client:
        yield client


def test_ingest_query_and_partition_isolation(client):
    text = "The candidate designed payment retries with idempotency keys."
    response = client.post("/kb/ingest", json={"user_id": "session-a", "files": [text]})
    assert response.status_code == 200
    assert response.json()["track_id"].startswith("naive-session-a-")
    query = {"user_id": "session-a", "query": "payment retries", "lang": "en"}
    first = client.post("/kb/query", json=query)
    assert first.status_code == 200
    payload = first.json()
    assert payload["answer"] == text
    assert payload["citations"][0]["snippet"] == text
    assert client.post("/kb/query", json=query).json() == payload
    query["user_id"] = "session-b"
    assert client.post("/kb/query", json=query).json() == {"answer": "", "citations": []}


def test_failed_remote_source_is_not_indexed_as_text(client):
    # conftest 禁止真实 HTTP，此 URL 必定进入读取失败分支。
    source = "https://example.com/private-payment-notes"
    assert client.post("/kb/ingest", json={"user_id": "session-a", "files": [source]}).status_code == 200
    response = client.post("/kb/query", json={"user_id": "session-a", "query": "private payment", "lang": "en"})
    assert response.json() == {"answer": "", "citations": []}


@pytest.mark.parametrize("path,body", [
    ("/kb/ingest", {"user_id": "session-a", "files": ["payment retries"]}),
    ("/kb/query", {"user_id": "session-a", "query": "payment", "lang": "en"}),
])
def test_secret_gate_and_authorized_requests(client, monkeypatch, path, body):
    monkeypatch.setenv("LIGHTRAG_API_SECRET", "sidecar-test-secret")
    for headers in ({}, {"X-Internal-Secret": "wrong"}):
        assert client.post(path, json=body, headers=headers).status_code == 401
    assert client.get("/health").status_code == 200
    # 拒绝的入库没有产生可检索数据。
    headers = {"X-Internal-Secret": "sidecar-test-secret"}
    assert client.post("/kb/query", headers=headers, json={"user_id": "session-a", "query": "payment", "lang": "en"}).json() == {"answer": "", "citations": []}
    assert client.post(path, json=body, headers=headers).status_code == 200
