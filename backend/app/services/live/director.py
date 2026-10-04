"""后台观察计划覆盖率与可选难度建议，不推进游标或修改回答。"""

from __future__ import annotations

import asyncio
import contextlib

from ...core.logging import get_logger
from . import state
from .state import InterviewUserdata, Recommendation

log = get_logger(__name__)


class Director:
    """难度建议缓存仅用于观测；实时模型通过工具读取同一纯函数的结果。"""

    def __init__(
        self,
        userdata: InterviewUserdata,
        *,
        interval_sec: float = 5.0,
        enable_adaptive: bool = False,
    ) -> None:
        self._ud = userdata
        self._interval = interval_sec
        self._enable_adaptive = enable_adaptive
        self._task: asyncio.Task[None] | None = None
        self.coverage: float = 0.0
        # 仅启用自适应观测时更新，不能作为推进面试的状态。
        self.recommendation: Recommendation | None = None
        self.rationale: str = ""

    def start(self) -> None:
        """Launch the watcher as a detached background task."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def aclose(self) -> None:
        """Stop the watcher (idempotent)."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def _coverage(self) -> float:
        total = len(self._ud.ctx.plan.questions)
        if total == 0:
            return 1.0
        return min(self._ud.ctx.cursor, total) / total

    async def _run(self) -> None:
        try:
            while not state.is_complete(self._ud):
                self.coverage = self._coverage()
                log.info(
                    "director: coverage=%.0f%% (cursor=%d/%d, section=%s)",
                    self.coverage * 100,
                    self._ud.ctx.cursor,
                    len(self._ud.ctx.plan.questions),
                    state.current_section(self._ud),
                )
                if self._enable_adaptive:
                    sig = state.evaluate_difficulty(self._ud)
                    self.recommendation = sig.recommendation
                    self.rationale = sig.rationale
                    log.info(
                        "director: adaptive recommendation=%s (%s)",
                        sig.recommendation,
                        sig.rationale,
                    )
                await asyncio.sleep(self._interval)
            self.coverage = 1.0
            log.info("director: interview plan fully covered")
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            raise
        except Exception:
            log.exception("director: coverage watcher error (ignored)")
