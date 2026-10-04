"""直接验证内存仓库，并用 PostgREST 风格的记录客户端离线验证 Supabase 仓库。

替身在写入边界执行 JSON 编码，提前暴露不可序列化字段；不加载真实 SDK 或连接数据库。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.adapters.mock import build_mock
from app.repositories.repository import (
    MemoryRepository,
    SupabaseRepository,
)
from app.schemas.shared_models import (
    AnswerRecord,
    InterviewContext,
    LanguageMode,
    PrepRequest,
    ScoreCard,
)

# 从测试文件位置定位仓库迁移目录，不依赖运行工作目录。
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "infra" / "supabase" / "migrations"


def _run(coro):
    return asyncio.run(coro)


def _prep_request() -> PrepRequest:
    return PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="We are hiring a backend engineer.",
        company="Acme Payments",
        language_mode=LanguageMode(primary="en", mixed=False),
    )


def test_create_save_load_round_trip() -> None:
    repo = MemoryRepository()
    session_id = _run(repo.create_session(_prep_request()))
    assert session_id.startswith("sess_")
    assert repo.get_status(session_id) == "prep"

    ctx = build_mock(InterviewContext)
    assert isinstance(ctx, InterviewContext)
    _run(repo.save_context(session_id, ctx))

    loaded = _run(repo.load_context(session_id))
    assert loaded is not None
    assert loaded.model_dump() == ctx.model_dump()


def test_create_session_stamps_user_id() -> None:
    """所属用户必须写入会话行，否则报告页的用户所有权 RLS 无法读取该会话。"""
    repo = MemoryRepository()
    owner = "11111111-2222-3333-4444-555555555555"
    req = _prep_request().model_copy(update={"user_id": owner})
    session_id = _run(repo.create_session(req))
    assert repo._rows[session_id].user_id == owner

    # 免登录会话的所属用户为空值，不能以空字符串替代。
    anon_id = _run(repo.create_session(_prep_request()))
    assert repo._rows[anon_id].user_id is None


def test_save_coach_transcript_does_not_touch_interview_transcript() -> None:
    """教练转录与面试转录必须分别保存。"""
    repo = MemoryRepository()
    session_id = _run(repo.create_session(_prep_request()))
    interview = [{"role": "user", "text": "my interview answer"}]
    coach = [{"role": "assistant", "text": "let's drill system design"}]
    _run(repo.save_transcript(session_id, interview))
    _run(repo.save_coach_transcript(session_id, coach))
    row = repo._rows[session_id]
    assert row.transcript == interview
    assert row.coach_transcript == coach


def test_transcript_persistence_takes_independent_snapshots():
    repo = MemoryRepository()
    sid = _run(repo.create_session(_prep_request()))
    turns = [{"role": "user", "text": "saved", "metadata": {"tags": ["initial"]}}]
    _run(repo.save_transcript(sid, turns))
    _run(repo.save_coach_transcript(sid, turns))
    turns[0]["text"] = "mutated"
    turns[0]["metadata"]["tags"].append("new")
    row = repo._rows[sid]
    assert row.transcript[0]["text"] == row.coach_transcript[0]["text"] == "saved"
    assert row.transcript[0]["metadata"]["tags"] == ["initial"]


def test_update_status_and_missing_load() -> None:
    repo = MemoryRepository()
    session_id = _run(repo.create_session(_prep_request()))
    _run(repo.update_status(session_id, "ready"))
    assert repo.get_status(session_id) == "ready"
    assert _run(repo.load_context("sess_does_not_exist")) is None


def test_append_answer_and_save_scorecard() -> None:
    repo = MemoryRepository()
    session_id = _run(repo.create_session(_prep_request()))

    answer = AnswerRecord(
        question_id="q1",
        transcript="A mock answer.",
        started_at="2026-06-08T09:00:00Z",
        ended_at="2026-06-08T09:01:00Z",
    )
    _run(repo.append_answer(session_id, answer))

    scorecard = build_mock(ScoreCard)
    assert isinstance(scorecard, ScoreCard)
    _run(repo.save_scorecard(session_id, scorecard))

    _run(repo.save_transcript(session_id, [{"role": "agent", "text": "hi"}]))


# 通过记录客户端离线验证 Supabase 仓库。


class _FakeSupabaseResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeSessionsTable:
    """在共享内存行上模拟 PostgREST 链式调用并记录操作。

    写入时先执行 JSON 编码，复现 SDK 的序列化边界。
    """

    def __init__(self, store: dict[str, dict], log: list[tuple]) -> None:
        self._store = store
        self._log = log
        self._op: str | None = None
        self._payload: Any = None
        self._cols: str | None = None
        self._id: str | None = None

    def insert(self, payload: dict) -> _FakeSessionsTable:
        self._op, self._payload = "insert", payload
        return self

    def update(self, values: dict) -> _FakeSessionsTable:
        self._op, self._payload = "update", values
        return self

    def select(self, cols: str) -> _FakeSessionsTable:
        self._op, self._cols = "select", cols
        return self

    def eq(self, col: str, value: str) -> _FakeSessionsTable:
        assert col == "id", "the repository only ever filters by primary key"
        self._id = value
        return self

    def limit(self, n: int) -> _FakeSessionsTable:
        return self

    def execute(self) -> _FakeSupabaseResponse:
        if self._op == "insert":
            json.dumps(self._payload)  # 在 SDK 序列化边界暴露不可编码载荷。
            self._log.append(("insert", self._payload, self._payload["id"]))
            self._store[self._payload["id"]] = dict(self._payload)
            return _FakeSupabaseResponse([self._payload])
        if self._op == "update":
            json.dumps(self._payload)
            self._log.append(("update", self._payload, self._id))
            row = self._store.get(self._id or "")
            if row is not None:
                row.update(self._payload)
            return _FakeSupabaseResponse([row] if row is not None else [])
        assert self._op == "select"
        self._log.append(("select", self._cols, self._id))
        row = self._store.get(self._id or "")
        if row is None:
            return _FakeSupabaseResponse([])
        cols = [c.strip() for c in (self._cols or "").split(",")]
        return _FakeSupabaseResponse([{c: row.get(c) for c in cols}])


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.log: list[tuple] = []

    def table(self, name: str) -> _FakeSessionsTable:
        assert name == "sessions", "all session persistence lives in public.sessions"
        return _FakeSessionsTable(self.rows, self.log)


def _supabase_repo() -> tuple[SupabaseRepository, _FakeSupabaseClient]:
    repo = SupabaseRepository("https://example.supabase.co", "service-role-key")
    fake = _FakeSupabaseClient()
    repo._client = fake  # 注入客户端后不触发 _table 内的可选 SDK 导入。
    return repo, fake


def test_supabase_create_and_context_round_trip_payloads_are_json_safe() -> None:
    """写入上下文须可 JSON 编码，并能通过后续读取恢复相同模型。"""
    repo, fake = _supabase_repo()
    session_id = _run(repo.create_session(_prep_request()))
    assert session_id.startswith("sess_")
    assert fake.rows[session_id]["status"] == "prep"
    assert fake.rows[session_id]["jd_text"] == "We are hiring a backend engineer."

    ctx = build_mock(InterviewContext)
    assert isinstance(ctx, InterviewContext)
    _run(repo.save_context(session_id, ctx))

    loaded = _run(repo.load_context(session_id))
    assert loaded is not None
    assert loaded.model_dump() == ctx.model_dump()
    # 未知会话读取返回 None，供工作进程判断上下文尚不可用。
    assert _run(repo.load_context("sess_missing")) is None


def test_supabase_create_session_stamps_user_id_column() -> None:
    """Supabase 插入载荷也须写入所属用户，供报告页 RLS 校验。"""
    repo, fake = _supabase_repo()
    owner = "11111111-2222-3333-4444-555555555555"
    sid = _run(repo.create_session(_prep_request().model_copy(update={"user_id": owner})))
    assert fake.rows[sid]["user_id"] == owner
    anon = _run(repo.create_session(_prep_request()))
    assert fake.rows[anon]["user_id"] is None


def test_supabase_update_status_writes_each_live_terminal_status() -> None:
    """实时流程的各终态都须按原值写入状态列。"""
    repo, fake = _supabase_repo()
    sid = _run(repo.create_session(_prep_request()))
    for status in ("no_answers", "error", "complete"):
        _run(repo.update_status(sid, status))
        assert fake.rows[sid]["status"] == status
        assert ("update", {"status": status}, sid) in fake.log


def test_supabase_save_scorecard_payload_is_json_encodable() -> None:
    """评分卡载荷必须可 JSON 编码并原样存入 scorecard 列。"""
    repo, fake = _supabase_repo()
    sid = _run(repo.create_session(_prep_request()))
    sc = build_mock(ScoreCard)
    assert isinstance(sc, ScoreCard)
    _run(repo.save_scorecard(sid, sc))
    assert fake.rows[sid]["scorecard"] == sc.model_dump()


def test_completed_card_and_status_are_persisted_together():
    repo, fake = _supabase_repo()
    sid = _run(repo.create_session(_prep_request()))
    card = build_mock(ScoreCard)
    _run(repo.complete_session(sid, card))
    view = _run(repo.get_session_view(sid))
    assert view.status == "complete"
    assert view.scorecard == card
    assert ("update", {"scorecard": card.model_dump(), "status": "complete"}, sid) in fake.log

    memory = MemoryRepository()
    sid = _run(memory.create_session(_prep_request()))
    _run(memory.complete_session(sid, card))
    view = _run(memory.get_session_view(sid))
    assert view.status == "complete"
    assert view.scorecard == card


def test_supabase_append_answer_read_modify_writes_the_context_blob() -> None:
    """追加答案须同步权威上下文，供后续评分读取；尚无上下文时不写入。"""
    repo, fake = _supabase_repo()
    sid = _run(repo.create_session(_prep_request()))
    ctx = build_mock(InterviewContext)
    assert isinstance(ctx, InterviewContext)
    base_answers = len(ctx.answers)
    _run(repo.save_context(sid, ctx))

    answer = AnswerRecord(
        question_id="q1",
        transcript="A real spoken answer.",
        started_at="2026-06-11T09:00:00Z",
        ended_at="2026-06-11T09:01:00Z",
    )
    _run(repo.append_answer(sid, answer))

    loaded = _run(repo.load_context(sid))
    assert loaded is not None
    assert len(loaded.answers) == base_answers + 1
    assert loaded.answers[-1].model_dump() == answer.model_dump()

    # 无上下文时追加答案不能发出更新。
    sid2 = _run(repo.create_session(_prep_request()))
    updates_before = len([op for op, *_ in fake.log if op == "update"])
    _run(repo.append_answer(sid2, answer))
    assert len([op for op, *_ in fake.log if op == "update"]) == updates_before


def test_supabase_get_session_view_selects_migration_columns_and_maps_row() -> None:
    """会话读取列须与迁移一致，并映射到状态、进度、警告、上下文及评分卡。"""
    repo, fake = _supabase_repo()
    sid = _run(repo.create_session(_prep_request()))
    ctx = build_mock(InterviewContext)
    sc = build_mock(ScoreCard)
    _run(repo.save_context(sid, ctx))
    _run(repo.save_scorecard(sid, sc))
    _run(repo.mark_progress(sid, "cv_analysis"))
    _run(repo.mark_progress(sid, "cv_analysis"))
    _run(repo.add_warnings(sid, ["JD text is very short."]))
    _run(repo.update_status(sid, "complete"))

    view = _run(repo.get_session_view(sid))
    assert view is not None
    assert (view.session_id, view.status) == (sid, "complete")
    assert view.progress == ["cv_analysis"]
    assert view.prep_warnings == ["JD text is very short."]
    assert view.context is not None
    assert view.context.model_dump() == ctx.model_dump()
    assert view.scorecard is not None
    assert view.scorecard.model_dump() == sc.model_dump()

    # 用实际迁移定义约束读取列名，避免部署后才发现缺列。
    select_cols = [cols for op, cols, row_id in fake.log if op == "select" and row_id == sid][-1]
    assert select_cols == "id,status,progress,prep_warnings,context,scorecard"
    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    assert migration_files, f"no migrations found under {_MIGRATIONS_DIR}"
    migrations_sql = "".join(p.read_text() for p in migration_files)
    for col in select_cols.split(","):
        assert col in migrations_sql, f"selected column {col!r} not defined by any migration"

    # 未知会话由 API 转为 404，不能导致模型校验错误。
    assert _run(repo.get_session_view("sess_missing")) is None


def test_supabase_concurrent_mutations_preserve_all_updates(monkeypatch) -> None:
    repo, fake = _supabase_repo()

    async def yielding_exec(build):
        response = build()
        # 固定读取快照并强制交错写入，验证并行读改写不会丢失更新。
        response.data = json.loads(json.dumps(response.data))
        await asyncio.sleep(0)
        return response

    monkeypatch.setattr(repo, "_exec", yielding_exec)

    async def run():
        sid = await repo.create_session(_prep_request())
        ctx = build_mock(InterviewContext).model_copy(update={"session_id": sid, "answers": []})
        await repo.save_context(sid, ctx)
        answers = [
            AnswerRecord(
                question_id=f"q{i}", transcript=f"Answer {i}",
                started_at="2026-10-04T09:00:00Z", ended_at="2026-10-04T09:01:00Z",
            )
            for i in range(12)
        ]
        await asyncio.gather(
            *(repo.mark_progress(sid, f"step{i}") for i in range(12)),
            *(repo.mark_progress(sid, f"step{i}") for i in range(12)),
            *(repo.add_warnings(sid, [f"warning{i}", "shared"]) for i in range(12)),
            *(repo.append_answer(sid, answer) for answer in answers),
        )
        assert set(fake.rows[sid]["progress"]) == {f"step{i}" for i in range(12)}
        assert len(fake.rows[sid]["progress"]) == 12
        assert set(fake.rows[sid]["prep_warnings"]) == {
            "shared", *(f"warning{i}" for i in range(12)),
        }
        assert len(fake.rows[sid]["prep_warnings"]) == 13
        loaded = await repo.load_context(sid)
        assert loaded is not None
        assert loaded.answers == answers

    asyncio.run(run())
