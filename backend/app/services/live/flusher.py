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
    """转录或上下文变化后保存快照；失败会重试，但不保证固定时间内持久化。"""

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
        self._saved_transcript: list[dict] = []
        self._saved_context = copy.deepcopy(userdata.ctx)

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
        """检测同条数转录修正与回答/游标更新；失败时保留旧快照供下次重试。"""
        if (
            self._ud.transcript == self._saved_transcript
            and self._ud.ctx == self._saved_context
        ):
            return
        transcript = copy.deepcopy(self._ud.transcript)
        context = copy.deepcopy(self._ud.ctx)
        try:
            # 网络等待期间游标可能前进，先复制上下文以保持它与转录快照一致。
            await self._flush(context, transcript)
            # 仅在保存成功后推进水位，使失败的快照仍可在下一轮重试。
            self._saved_transcript = transcript
            self._saved_context = context
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
