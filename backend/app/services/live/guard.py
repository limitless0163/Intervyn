"""后台限制面试时长和转录轮数；触限后禁止新题，并为当前回答保留有界宽限期。"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.logging import get_logger
from . import state

if TYPE_CHECKING:
    from .state import InterviewUserdata

log = get_logger(__name__)

_WRAP_UP_LINE = (
    "We're at time for this interview, so let's wrap up here. "
    "Thank you — your feedback will be ready shortly."
)

# 收尾语会直接进入 TTS，须匹配面试语言；未覆盖的语言回退到英语。
_WRAP_UP_LINES: dict[str, str] = {
    "en": _WRAP_UP_LINE,
    "zh": "本次面试时间已到，我们就先进行到这里。感谢你的回答，面试反馈报告稍后就会准备好。",
    "vi": (
        "Đã hết thời gian cho buổi phỏng vấn, chúng ta kết thúc ở đây nhé. "
        "Cảm ơn bạn — phản hồi của bạn sẽ sẵn sàng trong giây lát."
    ),
}


def wrap_up_line(language: str | None) -> str:
    """The closing line for ``language`` (English fallback)."""
    return _WRAP_UP_LINES.get((language or "en").lower(), _WRAP_UP_LINE)


class SessionGuard:
    """实时会话的兜底限制，不阻塞正常轮次。

    answer_grace_sec 为触限后的回答宽限期，负值按零处理；
    time_fn 使用单调时钟，可注入以便测试。
    """

    def __init__(
        self,
        session: object,
        userdata: InterviewUserdata,
        *,
        max_duration_sec: float,
        max_turns: int,
        interval_sec: float = 2.0,
        time_fn: Callable[[], float] | None = None,
        wrap_up_line: str | None = None,
        answer_grace_sec: float = 300.0,
    ) -> None:
        self._session = session
        self._ud = userdata
        self._max_duration = float(max_duration_sec)
        self._max_turns = int(max_turns)
        self._interval = interval_sec
        self._time = time_fn or time.monotonic
        self._wrap_up_line = wrap_up_line or _WRAP_UP_LINE
        self._answer_grace = max(0.0, answer_grace_sec)
        self._limit_at: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._started_at: float = 0.0
        self.tripped: bool = False

    def start(self) -> None:
        """Launch the guard as a detached background task (idempotent)."""
        if self._task is None:
            self._started_at = self._time()
            self._task = asyncio.create_task(self._run())

    async def aclose(self) -> None:
        """Stop the guard (idempotent)."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def _limit_reached(self, elapsed: float) -> str | None:
        """Return a human reason if a ceiling is hit, else ``None``."""
        if elapsed >= self._max_duration:
            return f"max duration {self._max_duration:.0f}s reached"
        turns = len(self._ud.transcript)
        if turns >= self._max_turns:
            return f"max turns {self._max_turns} reached"
        return None

    async def _wrap_up(self, reason: str) -> None:
        """Say a closing line (best-effort) then shut the session down gracefully."""
        log.warning("session_guard: %s for %s — wrapping up", reason, self._ud.session_id)
        self._ud.closing = True
        # 先中断已排队的新题，避免收尾语等待新题播完后留下未回答的问题。
        with contextlib.suppress(Exception):
            await self._session.interrupt()  # type: ignore[attr-defined]
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                self._session.say(  # type: ignore[attr-defined]
                    self._wrap_up_line, allow_interruptions=False
                ), timeout=20.0,
            )
        with contextlib.suppress(Exception):
            self._session.shutdown(drain=True)  # type: ignore[attr-defined]

    async def _run(self) -> None:
        try:
            while True:
                elapsed = self._time() - self._started_at
                if getattr(self._ud, "closing", False):
                    return
                reason = self._limit_reached(elapsed)
                if reason is not None:
                    # 推进工具读取此标记后不再开新题；当前回答仍可在宽限期内结束。
                    self._ud.time_limit_reached = True
                    if self._limit_at is None:
                        self._limit_at = elapsed
                        log.info("session_guard: %s for %s; finishing current question",
                                 reason, self._ud.session_id)
                    busy = (
                        getattr(self._session, "agent_state", "listening")
                        in {"thinking", "speaking"}
                        or getattr(self._session, "user_state", "listening") == "speaking"
                    )
                    pending = hasattr(self._ud, "ctx") and not state.is_complete(self._ud)
                    if pending:
                        pending = not state.current_answer_saved(self._ud)
                    if (pending or busy) and elapsed - self._limit_at < self._answer_grace:
                        await asyncio.sleep(self._interval)
                        continue
                    self.tripped = True
                    await self._wrap_up(reason)
                    return
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            raise
        except Exception:
            log.exception("session_guard: watcher error (ignored)")
