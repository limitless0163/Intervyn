"""知识侧车的入库和检索客户端；未配置 LIGHTRAG_URL 时使用无状态离线模拟。

配置 LIGHTRAG_API_SECRET 后，调用侧车时携带 X-Internal-Secret。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ...schemas.shared_models import Citation
from ..logging import get_logger

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger(__name__)

_QUERY_TIMEOUT = 20.0
# 入库涉及解析和嵌入，超时额度高于检索；单位为秒。
_INGEST_TIMEOUT = 60.0


def _stub_track_id(user_id: str, files: list[str]) -> str:
    """根据分区键和文件数量生成稳定的离线任务标识；不区分文件正文。"""
    return f"trk-{user_id}-{len(files)}"


@runtime_checkable
class KnowledgeClient(Protocol):
    """以同一分区键执行知识入库和带引用的检索。"""

    async def search(
        self, user_id: str, query: str, lang: str
    ) -> tuple[str, list[Citation]]:
        """返回指定知识分区内的回答及引用列表。"""
        ...

    async def ingest(self, user_id: str, files: list[str]) -> str:
        """入库文本或 URL，返回任务标识；user_id 必须与后续检索使用的分区键一致。

        开源免登录流程以 session_id 作为该分区键。
        """
        ...


class HttpKnowledge:
    """通过 HTTP 调用知识侧车的入库和检索接口。"""

    def __init__(self, base_url: str, secret: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Secret": self._secret} if self._secret else {}

    async def search(
        self, user_id: str, query: str, lang: str
    ) -> tuple[str, list[Citation]]:
        import httpx

        payload = {"user_id": user_id, "query": query, "lang": lang}
        async with httpx.AsyncClient(timeout=_QUERY_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/kb/query", json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
        answer = data.get("answer", "")
        citations = [Citation(**c) for c in data.get("citations", [])]
        return (answer, citations)

    async def ingest(self, user_id: str, files: list[str]) -> str:
        import httpx

        payload = {"user_id": user_id, "files": files}
        async with httpx.AsyncClient(timeout=_INGEST_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/kb/ingest", json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("track_id", _stub_track_id(user_id, files))


class MockKnowledge:
    """返回固定格式的回答与引用；不联网，也不存储入库资料。"""

    async def search(
        self, user_id: str, query: str, lang: str
    ) -> tuple[str, list[Citation]]:
        answer = (
            f"Based on your prep materials, here is a grounded note on '{query}'. "
            "Focus your study on the highlighted competency and review the cited sources."
        )
        citations = [
            Citation(
                title="Prep notes",
                url="kb://prep-notes",
                snippet=f"Relevant guidance for '{query}' drawn from your uploaded materials.",
            ),
            Citation(
                title="Study coach summary",
                url="kb://study-coach",
                snippet="Key talking points and a worked example for this topic.",
            ),
        ]
        return (answer, citations)

    async def ingest(self, user_id: str, files: list[str]) -> str:
        """不保存资料，仅返回稳定的离线任务标识。"""
        return _stub_track_id(user_id, files)


def get_knowledge(settings: Settings) -> KnowledgeClient:
    """配置侧车地址时使用 HTTP 客户端，否则使用离线模拟。"""
    url = getattr(settings, "lightrag_url", None) or None
    if url:
        return HttpKnowledge(url, getattr(settings, "lightrag_api_secret", None))
    log.info("No LIGHTRAG_URL configured; using MockKnowledge (offline).")
    return MockKnowledge()
