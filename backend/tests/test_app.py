"""离线验证健康检查、准备 API 及输入拒绝流程。"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import repository as repo_mod


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_ok() -> None:
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_prep_endpoint_creates_ready_session() -> None:
    client = _client()
    body = {
        "cv_url": "https://example.com/cv.pdf",
        "jd_text": "Senior backend engineer building distributed payment systems in Python.",
        "company": "Acme Payments",
        "language_mode": {"primary": "en", "mixed": False},
    }
    resp = client.post("/api/prep", json=body)
    assert resp.status_code == 200

    data = resp.json()
    session_id = data["session_id"]
    assert session_id.startswith("sess_")

    # TestClient 等待后台任务结束后才返回，因此此时会话已 ready。
    view = client.get(f"/api/session/{session_id}")
    assert view.status_code == 200
    payload = view.json()
    assert payload["session_id"] == session_id
    assert payload["status"] == "ready"
    # 并行分支完成顺序不固定，只核对五个完成标记。
    assert set(payload["progress"]) == {
        "cv_analysis",
        "jd_analysis",
        "company_research",
        "gap_matching",
        "question_planner",
    }
    assert payload["context"] is not None
    assert payload["context"]["session_id"] == session_id

    # API 与测试共用当前进程的内存单例，便于直接检查写入结果。
    assert repo_mod._MEMORY_REPO.get_status(session_id) == "ready"


def test_session_endpoint_404_for_unknown_id() -> None:
    resp = _client().get("/api/session/sess_does_not_exist")
    assert resp.status_code == 404


def test_prep_endpoint_rejects_garbage_input() -> None:
    client = _client()
    body = {
        "cv_url": "asdasdasdasdasdasd",
        "jd_text": "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",
        "company": "Acme Payments",
        "language_mode": {"primary": "en", "mixed": False},
    }
    resp = client.post("/api/prep", json=body)
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    view = client.get(f"/api/session/{session_id}")
    assert view.status_code == 200
    payload = view.json()
    assert payload["status"] == "rejected"
    assert payload["prep_warnings"], "rejection must surface warnings to the UI"
    assert payload["context"] is None
