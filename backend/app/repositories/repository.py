"""统一会话存储接口；默认内存单例仅在当前进程内共享，Supabase 用于持久化。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import uuid4

from ..core.logging import get_logger
from ..schemas.shared_models import AnswerRecord, InterviewContext, PrepRequest, ScoreCard
from ..schemas.views import PrepStepStatus, SessionView
from ..utils.locks import KeyedLocks

if TYPE_CHECKING:
    from ..core.config import Settings

log = get_logger(__name__)


def _new_session_id() -> str:
    return f"sess_{uuid4().hex}"


@runtime_checkable
class SessionRepository(Protocol):
    """面试会话的存储契约。"""

    async def create_session(self, req: PrepRequest) -> str: ...

    async def save_context(self, session_id: str, ctx: InterviewContext) -> None: ...

    async def save_live_state(
        self, session_id: str, ctx: InterviewContext, turns: list[dict], status: str | None,
    ) -> None: ...

    async def load_context(self, session_id: str) -> InterviewContext | None: ...

    async def update_status(self, session_id: str, status: str) -> None: ...

    async def append_answer(self, session_id: str, a: AnswerRecord) -> None: ...

    async def save_scorecard(self, session_id: str, sc: ScoreCard) -> None: ...

    async def complete_session(self, session_id: str, sc: ScoreCard) -> None: ...

    async def save_transcript(self, session_id: str, turns: list[dict]) -> None: ...

    async def save_coach_transcript(self, session_id: str, turns: list[dict]) -> None: ...

    async def mark_progress(self, session_id: str, step: str) -> None: ...

    async def set_prep_step_status(
        self, session_id: str, step: str, status: PrepStepStatus,
    ) -> None: ...

    async def add_warnings(self, session_id: str, warnings: list[str]) -> None: ...

    async def get_session_view(self, session_id: str) -> SessionView | None: ...


@dataclass
class _SessionRow:
    id: str
    status: str = "prep"
    # 写入 Supabase 用户 ID，使报告页可通过 auth.uid() = user_id 的 RLS 读取会话。
    user_id: str | None = None
    company: str | None = None
    cv_url: str | None = None
    jd_text: str | None = None
    language_mode: dict[str, Any] = field(default_factory=lambda: {"primary": "en", "mixed": False})
    context: dict[str, Any] | None = None
    scorecard: dict[str, Any] | None = None
    transcript: list[dict] | None = None
    # 教练对话单独保存，避免覆盖面试原始记录。
    coach_transcript: list[dict] | None = None
    answers: list[dict] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    prep_step_statuses: dict[str, PrepStepStatus] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class MemoryRepository:
    """进程内会话存储；重启后丢失，也不与独立语音工作进程共享。"""

    def __init__(self) -> None:
        self._rows: dict[str, _SessionRow] = {}

    async def create_session(self, req: PrepRequest) -> str:
        session_id = _new_session_id()
        self._rows[session_id] = _SessionRow(
            id=session_id,
            status="prep",
            user_id=req.user_id,
            company=req.company,
            cv_url=req.cv_url,
            jd_text=req.jd_text,
            language_mode=req.language_mode.model_dump(),
        )
        return session_id

    async def save_context(self, session_id: str, ctx: InterviewContext) -> None:
        row = self._require(session_id)
        row.context = ctx.model_dump()

    async def save_live_state(
        self, session_id: str, ctx: InterviewContext, turns: list[dict], status: str | None,
    ) -> None:
        # 先构建快照，再一次替换；序列化失败也不能留下部分写入。
        row = self._require(session_id)
        context = ctx.model_dump()
        transcript = deepcopy(turns) if turns else row.transcript
        row.context, row.transcript = context, transcript
        if status is not None:
            row.status = status

    async def load_context(self, session_id: str) -> InterviewContext | None:
        row = self._rows.get(session_id)
        if row is None or row.context is None:
            return None
        return InterviewContext.model_validate(row.context)

    async def update_status(self, session_id: str, status: str) -> None:
        self._require(session_id).status = status

    async def append_answer(self, session_id: str, a: AnswerRecord) -> None:
        row = self._require(session_id)
        row.answers.append(a.model_dump())
        # 同步权威上下文，使后续评分读取到新增回答。
        if row.context is not None:
            ctx = InterviewContext.model_validate(row.context)
            ctx.answers.append(a)
            row.context = ctx.model_dump()

    async def save_scorecard(self, session_id: str, sc: ScoreCard) -> None:
        self._require(session_id).scorecard = sc.model_dump()

    async def complete_session(self, session_id: str, sc: ScoreCard) -> None:
        row = self._require(session_id)
        row.scorecard = sc.model_dump()
        row.status = "complete"

    async def save_transcript(self, session_id: str, turns: list[dict]) -> None:
        self._require(session_id).transcript = deepcopy(turns)

    async def save_coach_transcript(self, session_id: str, turns: list[dict]) -> None:
        self._require(session_id).coach_transcript = deepcopy(turns)

    async def mark_progress(self, session_id: str, step: str) -> None:
        row = self._require(session_id)
        if step not in row.progress:
            row.progress.append(step)

    async def add_warnings(self, session_id: str, warnings: list[str]) -> None:
        row = self._require(session_id)
        for w in warnings:
            if w not in row.warnings:
                row.warnings.append(w)

    async def set_prep_step_status(
        self, session_id: str, step: str, status: PrepStepStatus,
    ) -> None:
        self._require(session_id).prep_step_statuses[step] = status

    async def get_session_view(self, session_id: str) -> SessionView | None:
        row = self._rows.get(session_id)
        if row is None:
            return None
        context = (
            InterviewContext.model_validate(row.context) if row.context else None
        )
        scorecard = (
            ScoreCard.model_validate(row.scorecard) if row.scorecard else None
        )
        return SessionView(
            session_id=row.id,
            status=row.status,
            progress=list(row.progress),
            prep_step_statuses=dict(row.prep_step_statuses),
            prep_warnings=list(row.warnings),
            context=context,
            scorecard=scorecard,
        )

    # 仅供测试和状态检查使用，不属于仓库协议。
    def get_status(self, session_id: str) -> str | None:
        row = self._rows.get(session_id)
        return row.status if row else None

    def _require(self, session_id: str) -> _SessionRow:
        row = self._rows.get(session_id)
        if row is None:
            raise KeyError(f"Unknown session_id: {session_id}")
        return row


class SupabaseRepository:
    """通过延迟导入的 Supabase SDK 持久化 public.sessions。

    本实例按会话串行化读改写；跨进程更新仍需数据库级协调。
    """

    def __init__(self, url: str, service_role_key: str) -> None:
        self._url = url
        self._key = service_role_key
        self._client: Any | None = None
        self._client_lock = Lock()
        # 准备图并行分支会同时修改进度/警告；串行化本实例的读改写，防止丢失更新。
        self._mutation_locks = KeyedLocks()

    def _table(self) -> Any:
        # _table 在线程池中调用，首次并发访问也只能创建一个连接池。
        with self._client_lock:
            if self._client is None:
                try:
                    from supabase import create_client
                except ImportError as exc:  # pragma: no cover - 依赖可选 SDK
                    raise RuntimeError(
                        "supabase is not installed; install the 'supabase' extra."
                    ) from exc
                self._client = create_client(self._url, self._key)
        return self._client.table("sessions")

    async def _exec(self, build: Any) -> Any:
        """在线程中执行同步 SDK 调用，避免阻塞 API 的异步事件循环。"""
        import asyncio

        # 取消协程不能停止同步 SDK 的线程。等待它真正结束才释放外层会话锁，
        # 否则迟到写入可能覆盖下一次请求的更新。SDK 自身的网络时限仍然生效。
        task = asyncio.create_task(asyncio.to_thread(build))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:  # noqa: BLE001 - 线程失败也必须保留调用方取消语义
                    break
            # 获取线程异常，避免产生无人读取的任务异常；保留原取消语义。
            if not task.cancelled():
                task.exception()
            raise

    async def create_session(self, req: PrepRequest) -> str:
        session_id = _new_session_id()
        payload = {
            "id": session_id,
            "status": "prep",
            # 持久化所属用户以满足报告页 RLS；离线路径允许为空。
            "user_id": req.user_id,
            "company": req.company,
            "cv_url": req.cv_url,
            "jd_text": req.jd_text,
            "language_mode": req.language_mode.model_dump(),
            "progress": [],
            "prep_warnings": [],
        }
        await self._exec(lambda: self._table().insert(payload).execute())
        return session_id

    async def save_context(self, session_id: str, ctx: InterviewContext) -> None:
        async with self._mutation_locks.get(session_id):
            await self._update(session_id, {"context": ctx.model_dump()})

    async def save_live_state(
        self, session_id: str, ctx: InterviewContext, turns: list[dict], status: str | None,
    ) -> None:
        values: dict[str, Any] = {"context": ctx.model_dump()}
        if turns:
            values["transcript"] = deepcopy(turns)
        if status is not None:
            values["status"] = status
        async with self._mutation_locks.get(session_id):
            await self._update(session_id, values)

    async def load_context(self, session_id: str) -> InterviewContext | None:
        def _build() -> Any:
            return self._table().select("context").eq("id", session_id).limit(1).execute()

        resp = await self._exec(_build)
        rows = getattr(resp, "data", None) or []
        if not rows or not rows[0].get("context"):
            return None
        return InterviewContext.model_validate(rows[0]["context"])

    async def update_status(self, session_id: str, status: str) -> None:
        await self._update(session_id, {"status": status})

    async def append_answer(self, session_id: str, a: AnswerRecord) -> None:
        def _build() -> Any:
            return self._table().select("context").eq("id", session_id).limit(1).execute()

        async with self._mutation_locks.get(session_id):
            resp = await self._exec(_build)
            rows = getattr(resp, "data", None) or []
            if not rows or not rows[0].get("context"):
                return
            ctx = InterviewContext.model_validate(rows[0]["context"])
            ctx.answers.append(a)
            await self._update(session_id, {"context": ctx.model_dump()})

    async def save_scorecard(self, session_id: str, sc: ScoreCard) -> None:
        await self._update(session_id, {"scorecard": sc.model_dump()})

    async def complete_session(self, session_id: str, sc: ScoreCard) -> None:
        # 一个数据库更新同时保存成绩和终态，避免第二次写入失败留下 scoring 残态。
        await self._update(session_id, {"scorecard": sc.model_dump(), "status": "complete"})

    async def save_transcript(self, session_id: str, turns: list[dict]) -> None:
        await self._update(session_id, {"transcript": list(turns)})

    async def save_coach_transcript(self, session_id: str, turns: list[dict]) -> None:
        # 依赖迁移 0004；缺列错误交由调用方处理，本方法不吞掉异常。
        await self._update(session_id, {"coach_transcript": list(turns)})

    async def mark_progress(self, session_id: str, step: str) -> None:
        def _build() -> Any:
            return self._table().select("progress").eq("id", session_id).limit(1).execute()

        async with self._mutation_locks.get(session_id):
            resp = await self._exec(_build)
            rows = getattr(resp, "data", None) or []
            progress = list(rows[0].get("progress") or []) if rows else []
            if step not in progress:
                progress.append(step)
                await self._update(session_id, {"progress": progress})

    async def add_warnings(self, session_id: str, warnings: list[str]) -> None:
        if not warnings:
            return

        def _build() -> Any:
            return self._table().select("prep_warnings").eq("id", session_id).limit(1).execute()

        async with self._mutation_locks.get(session_id):
            resp = await self._exec(_build)
            rows = getattr(resp, "data", None) or []
            existing = list(rows[0].get("prep_warnings") or []) if rows else []
            changed = False
            for w in warnings:
                if w not in existing:
                    existing.append(w)
                    changed = True
            if changed:
                await self._update(session_id, {"prep_warnings": existing})

    async def set_prep_step_status(
        self, session_id: str, step: str, status: PrepStepStatus,
    ) -> None:
        def _build() -> Any:
            return (self._table().select("prep_step_statuses")
                    .eq("id", session_id).limit(1).execute())

        async with self._mutation_locks.get(session_id):
            resp = await self._exec(_build)
            rows = getattr(resp, "data", None) or []
            statuses = dict(rows[0].get("prep_step_statuses") or {}) if rows else {}
            statuses[step] = status
            await self._update(session_id, {"prep_step_statuses": statuses})

    async def get_session_view(self, session_id: str) -> SessionView | None:
        def _build() -> Any:
            return (
                self._table()
                .select("id,status,progress,prep_step_statuses,prep_warnings,context,scorecard")
                .eq("id", session_id)
                .limit(1)
                .execute()
            )

        resp = await self._exec(_build)
        rows = getattr(resp, "data", None) or []
        if not rows:
            return None
        row = rows[0]
        ctx_data = row.get("context")
        context = InterviewContext.model_validate(ctx_data) if ctx_data else None
        sc_data = row.get("scorecard")
        scorecard = ScoreCard.model_validate(sc_data) if sc_data else None
        return SessionView(
            session_id=row["id"],
            status=row.get("status", "prep"),
            progress=list(row.get("progress") or []),
            prep_step_statuses=dict(row.get("prep_step_statuses") or {}),
            prep_warnings=list(row.get("prep_warnings") or []),
            context=context,
            scorecard=scorecard,
        )

    async def _update(self, session_id: str, values: dict[str, Any]) -> None:
        await self._exec(lambda: self._table().update(values).eq("id", session_id).execute())


# 依赖组装可重复执行，但内存会话必须在同一进程内复用。
_MEMORY_REPO = MemoryRepository()


def get_repository(settings: Settings) -> SessionRepository:
    """完整配置 Supabase 时使用持久化仓库，否则复用当前进程的内存仓库。"""
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRepository(settings.supabase_url, settings.supabase_service_role_key)
    if settings.supabase_url or settings.supabase_service_role_key:
        # 半配置通常是部署错误，显式告警以免误以为会话已持久化。
        log.error(
            "Supabase is PARTIALLY configured (need BOTH SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY); falling back to the in-memory store — "
            "sessions will NOT survive a restart."
        )
    return _MEMORY_REPO
