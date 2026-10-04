"""在实时对话路径外定期保存转录，减少进程异常退出时未保存的内容。"""

from __future__ import annotations

import asyncio
import contextlib
import copy
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from ...core.logging import get_logger

if TYPE_CHECKING:
    from ...schemas.shared_models import InterviewContext
    from .state import InterviewUserdata

log = get_logger(__name__)

FlushFn = Callable[["InterviewContext", list[dict]], Awaitable[None]]


class TranscriptFlusher:
    """仅在转录增长后保存上下文快照；失败会重试，但不保证固定时间内持久化。"""

    def __init__(
        self,
        userdata: InterviewUserdata,
        flush: FlushFn,
        *,
        interval_sec: float = 20.0,
    ) -> None:
        self._ud = userdata
        self._flush = flush
        self._interval = float(interval_sec)
        self._task: asyncio.Task[None] | None = None
        self._last_len = 0

    def start(self) -> None:
        """启动后台检查点任务；重复调用不重复启动，非正间隔禁用检查点。"""
        if self._interval <= 0:
            return
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def aclose(self) -> None:
        """取消并等待检查点任务结束，可重复调用。"""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _checkpoint(self) -> None:
        """仅在转录条数增长时保存快照，成功后更新已保存水位。"""
        transcript = copy.deepcopy(self._ud.transcript)
        if len(transcript) <= self._last_len:
            return
        try:
            # 网络等待期间游标可能前进，先复制上下文以保持它与转录快照一致。
            await self._flush(copy.deepcopy(self._ud.ctx), transcript)
            # 仅在保存成功后推进水位，使失败的快照仍可在下一轮重试。
            self._last_len = len(transcript)
        except Exception:
            log.exception("transcript_flusher: checkpoint failed; will retry")

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                await self._checkpoint()
        except asyncio.CancelledError:  # pragma: no cover - 后台任务取消路径
            raise
        except Exception:
            log.exception("transcript_flusher: checkpoint loop error (ignored)")
