"""协调当前 API 进程中的会话状态与语音回写，防止评分读取到变化中的上下文。"""

from __future__ import annotations

from ..repositories.repository import SessionRepository
from ..schemas.shared_models import InterviewContext
from ..utils.locks import KeyedLocks

session_mutations = KeyedLocks()
_CLOSED_FOR_LIVE_WRITES = {"scoring", "complete", "no_answers", "error", "rejected"}


class SessionNotFoundError(LookupError):
    """会话不存在。"""


class SessionConflictError(RuntimeError):
    """会话当前状态不允许语音回写。"""


class SessionIdentityError(ValueError):
    """上下文与目标会话身份不一致。"""


async def save_live_result(
    session_id: str,
    context: InterviewContext,
    transcript: list[dict],
    status: str | None,
    repo: SessionRepository,
) -> None:
    """在同一短锁内检查状态并回写；未知终态提示沿用原有忽略行为。"""
    async with session_mutations.get(session_id):
        view = await repo.get_session_view(session_id)
        if view is None:
            raise SessionNotFoundError("Unknown session_id")
        if context.session_id != session_id:
            raise SessionIdentityError("Context session_id must match the URL")
        if view.status in _CLOSED_FOR_LIVE_WRITES:
            raise SessionConflictError(f"Session already {view.status}")
        if transcript:
            await repo.save_transcript(session_id, transcript)
        await repo.save_context(session_id, context)
        if status in {"no_answers", "error"}:
            await repo.update_status(session_id, status)
