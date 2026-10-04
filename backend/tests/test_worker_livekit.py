"""依赖 livekit 扩展的工作进程回归测试，扩展缺失时跳过。

离线验证真实插件构造、转录监听、语言路由及本地组件选择；
以房间、提供方和 HTTP 替身驱动真实关闭回调，核对恢复、回写及评分顺序。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

pytest.importorskip("livekit.agents")

from app.api.routes.session import LiveResultRequest
from app.dependencies.container import build_deps
from app.schemas.shared_models import (
    InterviewContext,
    LanguageMode,
    PrepRequest,
)
from app.services.live import state, worker
from app.services.live.state import InterviewUserdata
from app.services.prep import run_prep


def _build_context() -> InterviewContext:
    """运行模拟准备流程并读取有效面试上下文。"""
    deps = build_deps()
    req = PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary="en", mixed=False),
    )
    session_id = asyncio.run(run_prep(req, deps))
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    return ctx


def _userdata_two_sections() -> InterviewUserdata:
    """为单题模拟计划追加不同环节的题目，观察游标推进后的题号标记。"""
    ctx = _build_context()
    first = ctx.plan.questions[0]
    second = first.model_copy(update={"id": "q_behavioral", "section": "behavioral"})
    ctx.plan.questions.append(second)
    return InterviewUserdata(ctx=ctx, session_id=ctx.session_id)


class FakeAgentSession:
    """模拟 AgentSession 的事件注册接口，支持装饰器与直接回调两种注册方式。

    emit 同步执行已注册处理器，复现转录监听所依赖的 SDK 行为。
    """

    def __init__(self) -> None:
        self.handlers: dict[str, list[Callable[..., Any]]] = {}

    def on(
        self, event: str, callback: Callable[..., Any] | None = None
    ) -> Callable[..., Any]:
        if callback is not None:
            self.handlers.setdefault(event, []).append(callback)
            return callback

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.handlers.setdefault(event, []).append(fn)
            return fn

        return decorator

    def emit(self, event: str, ev: Any) -> None:
        for handler in self.handlers.get(event, []):
            handler(ev)


def _item_event(role: Any, text: Any) -> SimpleNamespace:
    """构造包含角色和正文的会话发言事件替身。"""
    return SimpleNamespace(item=SimpleNamespace(role=role, text_content=text))


def test_wire_transcript_capture_tags_turns() -> None:
    """每个已提交轮次须带发言时的活动题号，供关闭时按题恢复答案。"""
    ud = _userdata_two_sections()
    q1 = state.current_question(ud)
    assert q1 is not None

    session = FakeAgentSession()
    worker.wire_transcript_capture(session, ud)
    assert session.handlers.get("conversation_item_added"), (
        "wire_transcript_capture must register on conversation_item_added"
    )

    session.emit(
        "conversation_item_added",
        _item_event("user", "I traced a race condition in our ledger writer."),
    )
    assert ud.transcript == [
        {
            "role": "user",
            "text": "I traced a race condition in our ledger writer.",
            "question_id": q1.id,
        }
    ]

    # 推进后的新发言必须使用新题号，不能沿用上一题标记。
    state.advance(ud)
    session.emit(
        "conversation_item_added",
        _item_event("assistant", "Tell me about a time you led a team."),
    )
    assert ud.transcript[-1] == {
        "role": "assistant",
        "text": "Tell me about a time you led a team.",
        "question_id": "q_behavioral",
    }
    assert len(ud.transcript) == 2


def test_wire_transcript_capture_ignores_non_turns() -> None:
    """非候选人或智能体角色，以及空正文事件，均不能进入转录。"""
    ud = _userdata_two_sections()
    session = FakeAgentSession()
    worker.wire_transcript_capture(session, ud)

    session.emit("conversation_item_added", _item_event(None, "text with no role"))
    session.emit("conversation_item_added", _item_event("user", ""))
    session.emit("conversation_item_added", _item_event("user", None))
    session.emit("conversation_item_added", _item_event("assistant", ""))
    session.emit("conversation_item_added", _item_event("system", "function call noise"))

    assert ud.transcript == []


def test_deepgram_stt_kwargs_are_valid() -> None:
    """用实际 Deepgram 插件校验参数签名及两种端点时窗，构造时不建立网络连接。"""
    pytest.importorskip("livekit.plugins.deepgram")

    stt_en = worker._deepgram_stt("en", "nova-3", api_key="x")
    stt_vi = worker._deepgram_stt("vi", "nova-2", api_key="x")

    assert stt_en._opts.model == "nova-3"
    assert stt_en._opts.language == "en"
    assert stt_en._opts.endpointing_ms == 25

    assert stt_vi._opts.model == "nova-2"
    assert stt_vi._opts.language == "vi"
    assert stt_vi._opts.endpointing_ms == 300
    assert stt_vi._opts.smart_format is True
    assert stt_en._opts.smart_format is True

    # nova-2 不启用 nova-3 专用数字参数，避免非英语流式转写无结果。
    assert stt_en._opts.numerals is True
    assert stt_vi._opts.numerals is False


def test_build_stt_language_routing() -> None:
    """验证固定路由：越南语使用 nova-2，英语及 mixed 会话使用 nova-3。"""
    pytest.importorskip("livekit.plugins.deepgram")
    settings = SimpleNamespace(stt_provider="deepgram", deepgram_api_key="x")

    vi = worker.build_stt(settings, "vi")
    assert (vi._opts.model, str(vi._opts.language)) == ("nova-2", "vi")

    en = worker.build_stt(settings, "en")
    assert (en._opts.model, str(en._opts.language)) == ("nova-3", "en")

    mixed = worker.build_stt(settings, "vi", mixed=True)
    assert (mixed._opts.model, str(mixed._opts.language)) == ("nova-3", "multi")


# 关闭逻辑是入口内部回调，需驱动真实入口捕获注册函数，再替换外部接口验证顺序。

_SPOKEN = (
    "I led the incident response when our payments ledger started double-charging "
    "customers, traced it to a race between the retry worker and the settlement "
    "job, and added an idempotency key on every write."
)


class _RecordingHttpx:
    """记录 HTTP 请求而不联网，并在 json 参数边界执行 JSON 编码以复现真实客户端约束。"""

    def __init__(self, live_result_ok: bool = True) -> None:
        self.posts: list[tuple[str, Any]] = []
        self.live_result_ok = live_result_ok

    def urls(self) -> list[str]:
        return [url for url, _ in self.posts]

    def client_cls(self) -> type:
        recorder = self
        dumps = json.dumps

        class _Client:
            def __init__(self, *args: Any, **kwargs: Any) -> None: ...

            async def __aenter__(self) -> _Client:  # noqa: PYI034 - 最小接口测试替身
                return self

            async def __aexit__(self, *exc: object) -> bool:
                return False

            async def post(
                self, url: str, json: Any = None, headers: Any = None
            ) -> SimpleNamespace:
                dumps(json)  # 模拟真实客户端在 json 参数处的编码边界。
                recorder.posts.append((url, json))
                if url.endswith("/live-result") and not recorder.live_result_ok:
                    raise RuntimeError("api unreachable")
                return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

        return _Client


class _RecordingRepo:
    """包装真实仓库并记录 API 失败后直接回写的调用顺序。"""

    def __init__(self, inner: Any, fail_save_context: bool = False) -> None:
        self.inner = inner
        self.calls: list[tuple[str, str]] = []
        self.fail_save_context = fail_save_context

    async def save_transcript(self, session_id: str, turns: list[dict]) -> None:
        self.calls.append(("save_transcript", session_id))
        await self.inner.save_transcript(session_id, turns)

    async def save_context(self, session_id: str, ctx: Any) -> None:
        self.calls.append(("save_context", session_id))
        if self.fail_save_context:
            raise RuntimeError("store down")
        await self.inner.save_context(session_id, ctx)

    async def update_status(self, session_id: str, status: str) -> None:
        self.calls.append((f"update_status:{status}", session_id))
        await self.inner.update_status(session_id, status)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class _FakeRoom(FakeAgentSession):
    """提供房间身份字段及事件注册接口；元数据为空时以房间名作为会话 ID。"""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.metadata = None
        self.remote_participants: dict[str, Any] = {}


class _FakeJobContext:
    def __init__(self, room: _FakeRoom) -> None:
        self.room = room
        self.proc = SimpleNamespace(userdata={})
        self.shutdown_callbacks: list[Callable[[], Any]] = []

    async def connect(self) -> None:
        return None

    def add_shutdown_callback(self, cb: Callable[[], Any]) -> None:
        self.shutdown_callbacks.append(cb)


class _FakeLifecycle:
    """替代后台 Director 和 SessionGuard，提供同步启动与异步关闭。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def start(self) -> None: ...

    async def aclose(self) -> None: ...


class _FakeUsageCollector:
    def collect(self, m: Any) -> None: ...

    def get_summary(self) -> dict:
        return {}


def _drive_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    *,
    live_result_ok: bool = True,
    fail_save_context: bool = False,
    fail_trace_close: bool = False,
) -> SimpleNamespace:
    """离线运行真实 entrypoint 并捕获注册的关闭回调，仅替换外部协作接口。

    返回回调、会话状态及 HTTP/仓库记录器，供验证实际恢复、回写和评分分支。
    """
    interview_ctx = _build_context()
    session_id = interview_ctx.session_id

    rec_http = _RecordingHttpx(live_result_ok=live_result_ok)
    rec_repo = _RecordingRepo(build_deps().repo, fail_save_context=fail_save_context)
    deps = replace(build_deps(), repo=rec_repo)

    async def _fake_load(sid: str, settings: Any) -> Any:
        assert sid == session_id
        return interview_ctx

    sessions: list[FakeAgentSession] = []

    class _FakeSession(FakeAgentSession):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__()
            self.kwargs = kwargs
            sessions.append(self)

        async def start(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(worker, "_load_context_via_api", _fake_load)
    # 房间及提供方均已替换，关闭回归不能要求真实 LiveKit 凭据。
    monkeypatch.setattr(worker, "_require_live_providers", lambda settings: None)
    monkeypatch.setattr(worker, "build_deps", lambda settings=None: deps)
    monkeypatch.setattr(worker, "AgentSession", _FakeSession)
    monkeypatch.setattr(
        worker, "Interviewer", lambda userdata: SimpleNamespace(userdata=userdata)
    )
    monkeypatch.setattr(worker, "Director", _FakeLifecycle)
    monkeypatch.setattr(worker, "SessionGuard", _FakeLifecycle)
    monkeypatch.setattr(
        worker, "metrics", SimpleNamespace(UsageCollector=_FakeUsageCollector)
    )
    for factory in ("build_stt", "build_llm", "build_tts", "build_vad"):
        monkeypatch.setattr(worker, factory, lambda *a, **k: None)
    monkeypatch.setattr(worker, "build_turn_handling", lambda *a, **k: {})
    monkeypatch.setattr(worker, "build_room_options", lambda *a, **k: None)
    monkeypatch.setattr(httpx, "AsyncClient", rec_http.client_cls())
    if fail_trace_close:
        class _FailingTrace:
            def __enter__(self) -> str:
                return "tr_failing"

            def __exit__(self, *exc: object) -> None:
                raise ValueError("trace token was created in a different Context")

        monkeypatch.setattr(worker, "start_trace", lambda *a, **k: _FailingTrace())

    job_ctx = _FakeJobContext(_FakeRoom(session_id))
    asyncio.run(worker.entrypoint(job_ctx))

    assert len(job_ctx.shutdown_callbacks) == 1, (
        "entrypoint must register exactly one shutdown callback"
    )
    assert len(sessions) == 1
    userdata = sessions[0].kwargs["userdata"]
    assert userdata.session_id == session_id

    return SimpleNamespace(
        shutdown=job_ctx.shutdown_callbacks[0],
        userdata=userdata,
        http=rec_http,
        repo=rec_repo,
        session_id=session_id,
    )


def test_shutdown_recovers_unsaved_answers_before_deciding_has_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实关闭回调须先恢复原话再判断有无答案，回写成功后才触发评分。"""
    drive = _drive_entrypoint(monkeypatch)
    ud = drive.userdata
    q1 = state.current_question(ud)
    assert q1 is not None

    state.add_turn(ud, "assistant", "Tell me about a hard production bug you fixed.")
    state.add_turn(ud, "user", _SPOKEN)
    assert ud.ctx.answers == [], "precondition: the model never called save_answer"

    asyncio.run(drive.shutdown())

    assert len(drive.http.posts) == 2, "exactly: live-result persist, then score"
    url, payload = drive.http.posts[0]
    assert url.endswith(f"/api/session/{drive.session_id}/live-result")
    assert payload["status"] is None, (
        "recovered speech counts as answers — no terminal no_answers hint"
    )
    answers = payload["context"]["answers"]
    assert [a["question_id"] for a in answers] == [q1.id]
    assert answers[0]["transcript"] == _SPOKEN
    # 持久化成功后才评分，且必须作用于当前会话。
    score_url, score_body = drive.http.posts[1]
    assert score_url.endswith("/api/score/start")
    assert score_body == {"session_id": drive.session_id}
    # API 回写成功后不得再执行直接仓库兜底。
    assert drive.repo.calls == []


def test_shutdown_continues_persist_and_scoring_when_trace_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """追踪关闭失败不能阻止已有回答的会话持久化和评分。"""
    drive = _drive_entrypoint(monkeypatch, fail_trace_close=True)
    state.add_turn(drive.userdata, "user", _SPOKEN)

    asyncio.run(drive.shutdown())

    assert drive.http.urls()[0].endswith("/live-result")
    assert drive.http.urls()[-1].endswith("/api/score/start")


def test_shutdown_payload_is_json_encodable_and_parses_as_live_result_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作进程载荷须可 JSON 编码，并满足 API 的 LiveResultRequest 契约。"""
    drive = _drive_entrypoint(monkeypatch)
    ud = drive.userdata
    state.add_turn(ud, "user", _SPOKEN)
    state.save_answer(
        ud,
        transcript=_SPOKEN,
        started_at="2026-06-11T09:00:00Z",
        ended_at="2026-06-11T09:02:00Z",
    )

    asyncio.run(drive.shutdown())

    url, payload = drive.http.posts[0]
    assert url.endswith("/live-result")
    json.dumps(payload)
    req = LiveResultRequest.model_validate(payload)
    assert req.transcript == ud.transcript
    assert [a.transcript for a in req.context.answers] == [_SPOKEN]
    assert req.status is None


def test_shutdown_silent_call_sends_no_answers_hint_and_skips_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有候选人发言时回写 no_answers 且不触发评分。"""
    drive = _drive_entrypoint(monkeypatch)
    state.add_turn(drive.userdata, "assistant", "Hello? Are you still there?")

    asyncio.run(drive.shutdown())

    url, payload = drive.http.posts[0]
    assert url.endswith("/live-result")
    assert payload["status"] == "no_answers"
    assert payload["context"]["answers"] == []
    assert not any(u.endswith("/api/score/start") for u in drive.http.urls())


def test_shutdown_blank_saved_answers_still_count_as_no_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空答案列表项不算有效回答，没有可恢复原话时仍须跳过评分。"""
    drive = _drive_entrypoint(monkeypatch)
    state.save_answer(drive.userdata, transcript="", started_at="", ended_at="")

    asyncio.run(drive.shutdown())

    assert drive.http.posts[0][1]["status"] == "no_answers"
    assert not any(u.endswith("/api/score/start") for u in drive.http.urls())


def test_shutdown_falls_back_to_repo_when_api_post_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API 回写失败后按转录、上下文顺序回写仓库；有答案且回写成功后继续触发评分。"""
    drive = _drive_entrypoint(monkeypatch, live_result_ok=False)
    ud = drive.userdata
    q1 = state.current_question(ud)
    assert q1 is not None
    state.add_turn(ud, "user", _SPOKEN)

    asyncio.run(drive.shutdown())

    # 先尝试 API 回写，再进入仓库兜底。
    assert drive.http.urls()[0].endswith("/live-result")
    # 兜底须按转录、上下文顺序回写。
    assert drive.repo.calls == [
        ("save_transcript", drive.session_id),
        ("save_context", drive.session_id),
    ]
    repo = build_deps().repo
    persisted = asyncio.run(repo.load_context(drive.session_id))
    assert persisted is not None
    assert [a.question_id for a in persisted.answers] == [q1.id]
    assert persisted.answers[0].transcript == _SPOKEN
    # 有有效答案时不能被兜底写成 no_answers。
    assert repo.get_status(drive.session_id) == "ready"
    assert drive.http.urls()[-1].endswith("/api/score/start")


def test_shutdown_repo_save_context_failure_marks_error_and_skips_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API 和上下文兜底写入都失败时标记 error，不能按旧的无回答上下文评分。"""
    drive = _drive_entrypoint(monkeypatch, live_result_ok=False, fail_save_context=True)
    state.add_turn(drive.userdata, "user", _SPOKEN)

    asyncio.run(drive.shutdown())

    assert ("update_status:error", drive.session_id) in drive.repo.calls
    assert build_deps().repo.get_status(drive.session_id) == "error"
    assert not any(u.endswith("/api/score/start") for u in drive.http.urls())


# 仅构造本地组件，不连接服务；验证音频分支、语言参数及本地配置优先级。


def _local_settings(**overrides):
    base = {
        "llm_provider": "mock",
        "stt_provider": "mock",
        "tts_provider": "mock",
        "ollama_base_url": "http://localhost:11434/v1",
        "ollama_model": "qwen3:8b",
        "ollama_model_live": "",
        "whisper_base_url": "http://localhost:8000/v1",
        "whisper_model": "Systran/faster-whisper-small",
        "kokoro_base_url": "http://localhost:8880/v1",
        "kokoro_model": "tts-1",
        "kokoro_voice": "",
        "kokoro_response_format": "pcm",
        "local_api_key": "local",
        "local_provider_timeout_sec": 30.0,
        "gemini_api_key": None,
        "elevenlabs_api_key": None,
        "elevenlabs_model": "eleven_flash_v2_5",
        "cartesia_api_key": None,
        "gemini_tts_model": "gemini-2.5-flash-preview-tts",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_llm_ollama_points_at_local_server() -> None:
    """显式本地模型必须指向本地地址，不能意外进入云端默认客户端。"""
    pytest.importorskip("livekit.plugins.openai")
    llm = worker.build_llm(_local_settings(llm_provider="ollama"))
    assert str(llm._client.base_url).startswith("http://localhost:11434")
    assert llm._opts.model == "qwen3:8b"


def test_build_llm_local_live_tier_overrides_the_prep_model() -> None:
    """配置 OLLAMA_MODEL_LIVE 时实时路径须优先使用该型号。"""
    pytest.importorskip("livekit.plugins.openai")
    llm = worker.build_llm(
        _local_settings(llm_provider="ollama", ollama_model_live="qwen3:1.7b")
    )
    assert llm._opts.model == "qwen3:1.7b"
    assert str(llm._client.base_url).startswith("http://localhost:11434")


def test_build_llm_local_live_tier_falls_back_when_unset() -> None:
    """实时型号留空时复用准备型号，不能将空型号传给插件或切到未下载模型。"""
    pytest.importorskip("livekit.plugins.openai")
    llm = worker.build_llm(_local_settings(llm_provider="ollama", ollama_model_live=""))
    assert llm._opts.model == "qwen3:8b"


def test_build_stt_whisper_wraps_in_stream_adapter() -> None:
    """批量 Whisper 必须通过 VAD 的 StreamAdapter 包装，才能驱动实时麦克风流。"""
    pytest.importorskip("livekit.plugins.openai")
    from livekit.plugins import openai as lk_openai

    stt = worker.build_stt(_local_settings(stt_provider="whisper"), "en", vad=SimpleNamespace())
    assert stt.capabilities.streaming is True
    assert isinstance(stt.wrapped_stt, lk_openai.STT)
    assert stt.wrapped_stt.capabilities.streaming is False
    assert str(stt.wrapped_stt._client.base_url).startswith("http://localhost:8000")


def test_build_stt_whisper_code_switching_uses_detect_language() -> None:
    """混合语言使用 detect_language，不能把 Deepgram 的 multi 标记传给 Whisper。"""
    pytest.importorskip("livekit.plugins.openai")
    stt = worker.build_stt(
        _local_settings(stt_provider="whisper"), "vi", mixed=True, vad=SimpleNamespace()
    )
    assert stt.wrapped_stt._opts.detect_language is True
    assert str(stt.wrapped_stt._opts.language) != "multi"


def test_build_tts_kokoro_uses_the_audio_branch_not_sse() -> None:
    """Kokoro 型号必须选择音频字节分支，误入 SSE 分支会静默丢失语音。"""
    pytest.importorskip("livekit.plugins.openai")
    from livekit.plugins.openai.tts import AUDIO_STREAM_MODELS

    tts = worker.build_tts(_local_settings(tts_provider="kokoro"), "en")
    assert tts._wrapped_tts._opts.model in AUDIO_STREAM_MODELS
    assert tts._wrapped_tts._opts.response_format == "pcm"
    # 批量 TTS 用流适配器逐句合成，避免等待整段回答才开始播报。
    assert tts.capabilities.streaming is True


def test_build_tts_kokoro_coerces_a_model_that_would_be_silent() -> None:
    tts = worker.build_tts(_local_settings(tts_provider="kokoro", kokoro_model="kokoro"), "en")
    assert tts._wrapped_tts._opts.model == "tts-1"


def test_build_tts_kokoro_picks_the_voice_from_the_language() -> None:
    """按声音 ID 选择语言，显式声音配置仍应优先。"""
    en = worker.build_tts(_local_settings(tts_provider="kokoro"), "en")
    ja = worker.build_tts(_local_settings(tts_provider="kokoro"), "ja")
    assert en._wrapped_tts._opts.voice == "af_heart"
    assert ja._wrapped_tts._opts.voice == "jf_alpha"
    pinned = worker.build_tts(
        _local_settings(tts_provider="kokoro", kokoro_voice="bf_emma"), "en"
    )
    assert pinned._wrapped_tts._opts.voice == "bf_emma"


def test_build_tts_kokoro_beats_the_cloud_language_reroute() -> None:
    """本地支持的语言不能因环境中的云端密钥而被意外切换到付费提供方。"""
    tts = worker.build_tts(
        _local_settings(tts_provider="kokoro", elevenlabs_api_key="x"), "ja"
    )
    assert tts._wrapped_tts._opts.voice == "jf_alpha"


def test_build_tts_kokoro_falls_back_for_a_language_it_cannot_speak() -> None:
    """本地没有对应语言声音时允许云端回退，避免用错误语言声音朗读。"""
    pytest.importorskip("livekit.plugins.elevenlabs")
    from livekit.plugins import elevenlabs

    tts = worker.build_tts(_local_settings(tts_provider="kokoro", elevenlabs_api_key="x"), "vi")
    assert isinstance(tts, elevenlabs.TTS), "vi must reroute to a voice that speaks it"


def test_build_conn_options_only_widens_for_local_providers() -> None:
    """本地组件组合扩大调用时限，普通云端组合保持 SDK 默认值。"""
    assert worker.build_conn_options(_local_settings()) is None
    assert worker.build_conn_options(_local_settings(llm_provider="gemini")) is None

    opts = worker.build_conn_options(_local_settings(llm_provider="ollama"))
    assert opts is not None
    assert opts.llm_conn_options.timeout == 30.0
    assert opts.stt_conn_options.timeout == 30.0
    # 限制本地重试次数，避免服务离线时长期卡住轮次。
    assert opts.llm_conn_options.max_retry == 1


def test_unreachable_local_providers_names_the_url_and_env_var() -> None:
    """本地服务不可达时启动检查须指出地址及配置名，避免首轮才暴露失败。"""
    settings = _local_settings(llm_provider="ollama", ollama_base_url="http://127.0.0.1:1/v1")
    problems = worker._unreachable_local_providers(settings)
    assert len(problems) == 1
    assert "OLLAMA_BASE_URL" in problems[0]
    assert "http://127.0.0.1:1/v1" in problems[0]

    # 空地址属于配置缺失，不能误报为连接失败。
    blank = worker._unreachable_local_providers(
        _local_settings(tts_provider="kokoro", kokoro_base_url="")
    )
    assert blank == ["KOKORO_BASE_URL (TTS_PROVIDER=kokoro)"]

    # 云端配置不应触发本地探测。
    assert worker._unreachable_local_providers(_local_settings(llm_provider="gemini")) == []


def test_local_provider_values_are_case_insensitive_and_aliased() -> None:
    """预检和工厂须共用忽略大小写的别名规则，防止本地配置被误选为云端。"""
    from livekit.plugins import openai as lk_openai

    for value in ("whisper", "Whisper", "QWEN3-ASR", "qwen-asr", "local", " speaches "):
        stt = worker.build_stt(
            _local_settings(stt_provider=value), "en", vad=SimpleNamespace()
        )
        assert isinstance(stt.wrapped_stt, lk_openai.STT), f"{value!r} must stay local"
        assert str(stt.wrapped_stt._client.base_url).startswith("http://localhost:8000")

    for value in ("ollama", "Ollama", "vllm", "lmstudio", "local"):
        llm = worker.build_llm(_local_settings(llm_provider=value))
        assert str(llm._client.base_url).startswith("http://localhost:11434"), value

    for value in ("kokoro", "Kokoro", "local"):
        tts = worker.build_tts(_local_settings(tts_provider=value), "en")
        assert tts._wrapped_tts._opts.voice == "af_heart", value

    # 未知提供方名称不能被视为本地服务。
    assert worker._unreachable_local_providers(_local_settings(stt_provider="deepgram")) == []


# 优先读取显式派发的会话 ID，避免陈旧房间元数据使工作进程读取错误上下文。


def _job_ctx(room_name: str, *, job_metadata=None, room_metadata=None):
    room = _FakeRoom(room_name)
    room.metadata = room_metadata
    ctx = _FakeJobContext(room)
    ctx.job = SimpleNamespace(metadata=job_metadata)
    return ctx


def test_session_id_prefers_dispatch_job_metadata() -> None:
    ctx = _job_ctx(
        "sess_room",
        job_metadata='{"session_id": "sess_dispatch"}',
        room_metadata='{"session_id": "sess_room_meta"}',
    )
    assert worker._session_id_from_room(ctx) == "sess_dispatch"


def test_session_id_falls_back_to_room_metadata_then_name() -> None:
    assert (
        worker._session_id_from_room(
            _job_ctx("sess_room", room_metadata='{"session_id": "sess_meta"}')
        )
        == "sess_meta"
    )
    assert worker._session_id_from_room(_job_ctx("sess_room")) == "sess_room"


def test_session_id_tolerates_malformed_job_metadata() -> None:
    ctx = _job_ctx("sess_room", job_metadata="not-json")
    assert worker._session_id_from_room(ctx) == "sess_room"


def test_worker_agent_name_default_matches_web_token() -> None:
    """工作进程派发名称须与网页令牌一致，否则房间无法分配智能体。"""
    from app.core.config import Settings

    assert Settings().livekit_agent_name == "intervyn-interviewer"


def test_load_context_with_retry_waits_for_prep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """准备期间加入房间时须持续等待上下文，不因首次未就绪就退出。"""
    ctx = _build_context()
    calls = {"n": 0}

    async def _flaky(sid: str, settings: Any) -> Any:
        calls["n"] += 1
        return None if calls["n"] < 3 else ctx

    monkeypatch.setattr(worker, "_load_context_via_api", _flaky)
    got = asyncio.run(
        worker._load_context_with_retry("sess_x", SimpleNamespace(), timeout_sec=30.0)
    )
    assert got is ctx
    assert calls["n"] == 3


def test_load_context_with_retry_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _never(sid: str, settings: Any) -> Any:
        return None

    monkeypatch.setattr(worker, "_load_context_via_api", _never)
    got = asyncio.run(
        worker._load_context_with_retry("sess_x", SimpleNamespace(), timeout_sec=0.1)
    )
    assert got is None
