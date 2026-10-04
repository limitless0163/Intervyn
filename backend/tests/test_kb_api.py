"""未配置侧车时离线验证入库任务标识及模拟知识回答。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _no_local_dotenv(monkeypatch, tmp_path):
    """隔离工作目录、环境和配置缓存，避免本地侧车配置影响测试选择或泄漏到后续测试。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIGHTRAG_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client() -> TestClient:
    return TestClient(create_app())


def test_kb_ingest_returns_track_id_offline() -> None:
    resp = _client().post(
        "/api/kb/ingest",
        json={"store_key": "user_x", "files": ["kb://doc-1", "kb://doc-2"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["track_id"], str)
    assert body["track_id"]


def test_kb_ingest_is_deterministic_offline() -> None:
    client = _client()
    payload = {"store_key": "user_x", "files": ["kb://doc-1", "kb://doc-2"]}
    first = client.post("/api/kb/ingest", json=payload).json()["track_id"]
    second = client.post("/api/kb/ingest", json=payload).json()["track_id"]
    assert first == second


def test_kb_query_returns_grounded_answer() -> None:
    resp = _client().post(
        "/api/kb/query",
        json={"store_key": "user_x", "query": "How do I structure a STAR answer?", "lang": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["answer"], str)
    assert body["answer"]
    # 此知识 API 默认返回模拟引用，区别于教练聊天的无检索引用策略。
    assert len(body["citations"]) >= 1


def test_failed_ingestion_does_not_return_a_fake_success_track_id(monkeypatch):
    from app.api.routes import kb

    async def ingest(*args):
        raise RuntimeError("sidecar offline")

    monkeypatch.setattr(kb, "build_deps", lambda: SimpleNamespace(knowledge=SimpleNamespace(ingest=ingest)))
    response = _client().post("/api/kb/ingest", json={"store_key": "u", "files": ["notes"]})
    assert response.status_code == 503
    assert "track_id" not in response.json()
