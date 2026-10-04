"""面试语音工作进程，需安装 livekit 扩展并配置 LiveKit 及语音提供方。

运行：python -m app.services.live.worker dev（生产模式为 start）。
从 API 读取准备上下文，实时工具只改本地状态；后台保存检查点，关闭时回写并请求后台评分。
"""

from __future__ import annotations

from livekit.agents import (
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    metrics,
)

from ...core.config import get_settings
from ...core.logging import get_logger
from ...core.observability import init_observability
from ...core.tracing import add_event, start_trace
from ...dependencies.container import build_deps
from ...schemas.shared_models import InterviewContext, RoomMetadata, ScoreRequest
from . import state
from .director import Director
from .flusher import TranscriptFlusher
from .guard import SessionGuard
from .guard import wrap_up_line as guard_wrap_up_line
from .interviewer import Interviewer
from .state import InterviewUserdata

log = get_logger(__name__)


def wire_audio_path_logging(ctx: JobContext, session) -> None:
    """记录音轨发布、订阅及说话状态，便于定位候选人音频未送达的问题。"""

    def _kind(pub) -> str:
        return str(getattr(pub, "kind", "?"))

    @ctx.room.on("participant_connected")
    def _on_participant(p) -> None:
        log.info("audio-path: participant connected identity=%s", p.identity)

    @ctx.room.on("track_published")
    def _on_published(pub, p) -> None:
        log.info("audio-path: track PUBLISHED kind=%s muted=%s by %s",
                 _kind(pub), getattr(pub, "muted", "?"), p.identity)

    @ctx.room.on("track_subscribed")
    def _on_subscribed(track, pub, p) -> None:
        log.info("audio-path: track SUBSCRIBED kind=%s from %s", _kind(pub), p.identity)

    @ctx.room.on("track_muted")
    def _on_muted(p, pub) -> None:
        log.info("audio-path: track MUTED kind=%s by %s", _kind(pub), p.identity)

    @ctx.room.on("track_unmuted")
    def _on_unmuted(p, pub) -> None:
        log.info("audio-path: track UNMUTED kind=%s by %s", _kind(pub), p.identity)

    for p in ctx.room.remote_participants.values():
        pubs = {sid: _kind(pub) for sid, pub in p.track_publications.items()}
        log.info("audio-path: already present identity=%s tracks=%s", p.identity, pubs)

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        log.info("audio-path: user state -> %s", getattr(ev, "new_state", ev))

    @session.on("user_input_transcribed")
    def _on_user_transcribed(ev) -> None:
        log.info("audio-path: user transcript final=%s len=%d",
                 getattr(ev, "is_final", "?"), len(getattr(ev, "transcript", "") or ""))

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        log.info("audio-path: agent state -> %s", getattr(ev, "new_state", ev))

    @session.on("close")
    def _on_close(ev) -> None:
        log.info("audio-path: session closed reason=%s error=%s",
                 getattr(ev, "reason", "?"), getattr(ev, "error", None))


def wire_transcript_capture(
    session, userdata: InterviewUserdata, *, tag_questions: bool = True
) -> None:
    """监听已提交的候选人转写及智能体发言，将原话存入内存转录并由回写流程保存。

    关闭时可从转录恢复工具未保存的回答；tag_questions=False 用于不属于答题的教练会话。
    """

    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None)
        if role in ("user", "assistant") and text:
            # 追踪只记录角色及文本长度，不保存原话；没有活动追踪或禁用时跳过。
            add_event("turn", {"role": role, "chars": len(text)})
            log.info("transcript: committed role=%s chars=%d cursor=%d interrupted=%s",
                     role, len(text), userdata.ctx.cursor, getattr(item, "interrupted", False))
            if tag_questions:
                state.add_turn(userdata, role, text)
            else:
                userdata.transcript.append({"role": role, "text": text})


# 工厂按提供方配置构造组件；配置不足的兜底组件仍可能依赖 SDK 环境凭据。


# 语音提供方使用会话主语言；混合语言的 Deepgram 路径使用 multi 标记。
_STT_LANG = {"en": "en", "vi": "vi", "es": "es", "zh": "zh", "fr": "fr", "de": "de", "ja": "ja"}
_TTS_LANG = {"en": "en", "vi": "vi", "es": "es", "zh": "zh", "fr": "fr", "de": "de", "ja": "ja"}


def _stt_lang(language: str, mixed: bool) -> str:
    return "multi" if mixed else _STT_LANG.get(language, "en")


def _deepgram_stt(lang: str, model: str, api_key=None):
    """按模型设置 Deepgram 端点时窗及数字格式化：nova-3 更短，nova-2 保留更长静音。

    避免非英语回答中的自然停顿被过早切成多个片段。
    """
    from livekit.plugins import deepgram

    is_nova3 = model == "nova-3"
    kwargs = dict(  # noqa: C408 - 后续需修改和展开关键字参数字典
        language=lang,
        model=model,
        punctuate=True,
        filler_words=True,
        vad_events=True,
        numerals=is_nova3,
        smart_format=True,
        endpointing_ms=25 if is_nova3 else 300,
    )
    if api_key is not None:
        kwargs["api_key"] = api_key
    return deepgram.STT(**kwargs)


def _local_whisper_stt(settings, language: str, mixed: bool, vad=None):
    """以 VAD 将麦克风流切成语句，再通过兼容接口批量转写并包装为流式能力。

    仅提供语句级最终结果，不提供逐词中间字幕；混合语言使用 detect_language，
    不把 Deepgram 的 multi 标记作为 Whisper 语言代码。
    """
    from livekit.agents import stt as agents_stt
    from livekit.plugins import openai

    return agents_stt.StreamAdapter(
        stt=openai.STT(
            model=settings.whisper_model,
            language=_STT_LANG.get(language, "en"),
            detect_language=mixed,
            base_url=settings.whisper_base_url,
            # 本地服务无需鉴权，但插件要求非空占位密钥。
            api_key=settings.local_api_key,
        ),
        vad=vad or build_vad(),
    )


def build_stt(settings, language="en", mixed=False, vad=None):
    """按提供方与语言构造转写组件；本地批量接口用 VAD 适配为语音流。"""
    lang = _stt_lang(language, mixed)
    provider = _provider(settings, "stt")
    # 先匹配显式本地配置，避免意外回退到云端。
    if provider in _LOCAL_STT:
        return _local_whisper_stt(settings, language, mixed, vad=vad)
    if provider == "livekit":
        from livekit.agents import inference

        kwargs = {"model": settings.livekit_stt_model}
        # 混合语言不指定固定语言，由提供方自行识别。
        if not mixed:
            kwargs["language"] = lang
        # 推理服务使用独立网关，房间 URL 不提供转写 WebSocket 接口。
        for name, value in (
            ("api_key", settings.livekit_api_key),
            ("api_secret", settings.livekit_api_secret),
        ):
            if value:
                kwargs[name] = value
        return inference.STT(**kwargs)
    # 非 en/multi 走 nova-2，避开曾出现的越南语流式转写无结果问题。
    model = "nova-3" if lang in ("en", "multi") else "nova-2"
    provider = _provider(settings, "stt")
    if provider == "deepgram" and settings.deepgram_api_key:
        return _deepgram_stt(lang, model, api_key=settings.deepgram_api_key)
    if provider == "soniox" and settings.soniox_api_key:
        from livekit.plugins import soniox

        return soniox.STT(api_key=settings.soniox_api_key)
    log.warning("build_stt: no configured STT provider/key; using Deepgram default")
    return _deepgram_stt(lang, model)


def _require_live_providers(settings) -> None:
    """会话启动前检查 LiveKit 必要配置、已选提供方密钥及本地服务连通性。

    仅检查密钥是否存在，不验证密钥有效性；未选择的提供方不要求其密钥。
    """
    missing: list[str] = []
    for name, value in (
        ("LIVEKIT_URL", settings.livekit_url),
        ("LIVEKIT_API_KEY", settings.livekit_api_key),
        ("LIVEKIT_API_SECRET", settings.livekit_api_secret),
    ):
        if not value:
            missing.append(name)
    llm = (settings.llm_provider or "").lower()
    if llm == "gemini" and not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY (LLM_PROVIDER=gemini)")
    elif llm == "openai" and not settings.openai_api_key:
        missing.append("OPENAI_API_KEY (LLM_PROVIDER=openai)")
    stt = (settings.stt_provider or "").lower()
    if stt == "deepgram" and not settings.deepgram_api_key:
        missing.append("DEEPGRAM_API_KEY (STT_PROVIDER=deepgram)")
    elif stt == "soniox" and not settings.soniox_api_key:
        missing.append("SONIOX_API_KEY (STT_PROVIDER=soniox)")
    tts = (settings.tts_provider or "").lower()
    if tts == "cartesia" and not settings.cartesia_api_key:
        missing.append("CARTESIA_API_KEY (TTS_PROVIDER=cartesia)")
    elif tts == "elevenlabs" and not settings.elevenlabs_api_key:
        missing.append("ELEVENLABS_API_KEY (TTS_PROVIDER=elevenlabs)")
    if "minimax" in {llm, tts} and not settings.minimax_api_key:
        missing.append("MINIMAX_API_KEY (LLM_PROVIDER/TTS_PROVIDER=minimax)")
    missing.extend(_unreachable_local_providers(settings))
    if missing:
        raise RuntimeError(
            "Live interview cannot start — missing provider credentials: "
            + "; ".join(missing)
        )


# 本地别名均指向兼容 OpenAI 的接口契约；预检与工厂必须使用同一别名集合。
_LOCAL_LLM = frozenset({"ollama", "vllm", "llamacpp", "lmstudio", "local"})
_LOCAL_STT = frozenset({"whisper", "faster-whisper", "qwen3-asr", "qwen-asr", "speaches", "local"})
_LOCAL_TTS = frozenset({"kokoro", "local"})

# 本地阶段映射到地址字段及错误提示中的环境变量名。
_LOCAL_PROVIDERS = {
    "llm_provider": (_LOCAL_LLM, "ollama_base_url", "OLLAMA_BASE_URL"),
    "stt_provider": (_LOCAL_STT, "whisper_base_url", "WHISPER_BASE_URL"),
    "tts_provider": (_LOCAL_TTS, "kokoro_base_url", "KOKORO_BASE_URL"),
}


def _provider(settings, stage: str) -> str:
    """统一去空白并转小写，使预检与组件工厂按同一提供方名称选择路径。"""
    return (getattr(settings, f"{stage}_provider", "") or "").strip().lower()


def _unreachable_local_providers(settings) -> list[str]:
    """对已选本地服务做限时连通探测，返回带地址及配置名的问题列表。

    只检查是否能建立 HTTP 连接，不验证模型是否已下载或接口功能完整。
    """
    import httpx

    problems: list[str] = []
    for field, (accepted, url_field, env_name) in _LOCAL_PROVIDERS.items():
        stage = field.removesuffix("_provider")
        selected = _provider(settings, stage)
        if selected not in accepted:
            continue
        base = (getattr(settings, url_field, "") or "").rstrip("/")
        if not base:
            problems.append(f"{env_name} ({field.upper()}={selected})")
            continue
        try:
            httpx.get(f"{base}/models", timeout=settings.local_probe_timeout_sec)
        except Exception as exc:  # noqa: BLE001 - 本地服务无法连接时阻止启动
            # HTTP 错误码仍证明服务可连接，此探测只将连接、DNS 或超时错误视为不可达。
            problems.append(f"{env_name}={base} unreachable ({type(exc).__name__}: {exc})")
    return problems


def build_llm(settings):
    """构造实时模型，优先采用显式本地配置及独立的语音型号。"""
    provider = _provider(settings, "llm")
    if provider in _LOCAL_LLM:
        from livekit.plugins import openai

        # 语音模型可单独选较小型号；留空时复用已配置的准备模型。
        model = settings.ollama_model_live or settings.ollama_model
        if settings.ollama_model_live:
            log.info(
                "build_llm: local live tier — turn path on %r (prep/scoring stays on %r)",
                settings.ollama_model_live,
                settings.ollama_model,
            )
        return openai.LLM(
            model=model,
            base_url=settings.ollama_base_url,
            api_key=settings.local_api_key,
        )
    if provider == "openai" and settings.openai_api_key:
        from livekit.plugins import openai

        return openai.LLM(model=settings.openai_model, api_key=settings.openai_api_key)
    if provider == "minimax" and settings.minimax_api_key:
        from .minimax_llm import MiniMaxLLM

        return MiniMaxLLM(
            model=settings.minimax_model_live or settings.minimax_model,
            base_url=f"{settings.minimax_base_url.rstrip('/')}/v1",
            api_key=settings.minimax_api_key,
        )
    if provider == "gemini" and settings.gemini_api_key:
        from livekit.plugins import google

        # 语音路径使用单独配置的实时模型。
        return google.LLM(model=settings.gemini_model_live, api_key=settings.gemini_api_key)
    log.warning("build_llm: no configured LLM provider/key; using OpenAI default")
    from livekit.plugins import openai

    return openai.LLM()


# 本实现使用的 Cartesia 语言集合；集合外优先 ElevenLabs，再按密钥尝试 Gemini。
_CARTESIA_LANGS = {"en", "es", "fr", "de", "ja", "zh", "pt", "hi", "it", "ko", "nl", "pl", "ru", "sv", "tr"}


# Kokoro 通过声音 ID 前缀选择语言；不支持的语言由工厂进入云端回退。
_KOKORO_VOICE = {
    "en": "af_heart",
    "ja": "jf_alpha",
    "zh": "zf_xiaobei",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "hi": "hf_alpha",
    "it": "if_sara",
    "pt": "pf_dora",
}


def _local_kokoro_tts(settings, language="en"):
    """按句包装本地 Kokoro 的批量合成，减少等待整段回答后才开始播报的延迟。"""
    from livekit.agents import tts as agents_tts
    from livekit.plugins import openai
    from livekit.plugins.openai.tts import AUDIO_STREAM_MODELS

    # 限制为插件的音频字节型号，避免误入 SSE 分支后无声且不报错。
    model = settings.kokoro_model
    if model not in AUDIO_STREAM_MODELS:
        log.warning(
            "build_tts: KOKORO_MODEL=%r is outside %s, which would produce SILENT "
            "audio with no error; using 'tts-1' instead (kokoro-fastapi ignores "
            "the model name).",
            model,
            sorted(AUDIO_STREAM_MODELS),
        )
        model = "tts-1"

    # 显式声音配置优先，否则按会话语言选择。
    voice = settings.kokoro_voice or _KOKORO_VOICE.get(language, "af_heart")

    return agents_tts.StreamAdapter(
        tts=openai.TTS(
            model=model,
            voice=voice,
            base_url=settings.kokoro_base_url,
            api_key=settings.local_api_key,
            response_format=settings.kokoro_response_format,
        )
    )


def build_tts(settings, language="en"):
    """优先匹配显式提供方，并按本实现的语言支持表选择可用回退声音。"""
    lang = _TTS_LANG.get(language, "en")
    provider = _provider(settings, "tts")
    needs_non_cartesia = language not in _CARTESIA_LANGS

    # 显式本地选择优先；无对应语言声音且未指定声音时才尝试云端回退。
    if provider in _LOCAL_TTS:
        if language in _KOKORO_VOICE or settings.kokoro_voice:
            return _local_kokoro_tts(settings, language)
        log.warning(
            "build_tts: Kokoro has no voice for %r; falling back to a cloud voice. "
            "Set KOKORO_VOICE to force a specific one.",
            language,
        )

    if provider == "minimax" and settings.minimax_api_key:
        from livekit.agents.tokenize import blingfire
        from livekit.plugins import minimax

        return minimax.TTS(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            model=settings.minimax_tts_model,
            voice=settings.minimax_tts_voice,
            speed=getattr(settings, "minimax_tts_speed", 1.0),
            emotion="neutral",
            text_normalization=True,
            # 按完整句子合成并保留足够上下文，避免中文逗号及短回应导致韵律碎片化。
            tokenizer=blingfire.SentenceTokenizer(
                min_token_len=50 if language in {"zh", "ja"} else 120,
            ),
            # 逐句刷新使用 PCM，避免复用已被上一句关闭的 MP3 解码器。
            audio_format="pcm",
        )

    # 显式选择 ElevenLabs 或语言不在 Cartesia 集合内时，优先使用已配置的 ElevenLabs。
    if (provider == "elevenlabs" or needs_non_cartesia) and settings.elevenlabs_api_key:
        from livekit.plugins import elevenlabs

        # 显式传入语言代码，避免多语言文字被按错误语言读出。
        return elevenlabs.TTS(
            api_key=settings.elevenlabs_api_key,
            model=settings.elevenlabs_model,
            voice_id="EXAVITQu4vr4xnSDxMaL",
            language=lang,
        )

    # 集合外语言且无 ElevenLabs 密钥时，尝试已配置的 Gemini 语音。
    if needs_non_cartesia and provider != "elevenlabs" and settings.gemini_api_key:
        from livekit.plugins.google.beta import GeminiTTS

        log.info("build_tts: %r unsupported by Cartesia; using Gemini TTS fallback", language)
        return GeminiTTS(model=settings.gemini_tts_model, api_key=settings.gemini_api_key)

    if provider == "cartesia" and settings.cartesia_api_key:
        from livekit.plugins import cartesia

        return cartesia.TTS(api_key=settings.cartesia_api_key, language=lang)
    log.warning("build_tts: no configured TTS provider/key; using Cartesia default")
    from livekit.plugins import cartesia

    return cartesia.TTS(language=lang)


# 本实现启用语义轮次检测的语言集合；其余采用较长静音端点，容纳句中停顿。
_EOU_MODEL_LANGS = frozenset(
    {"en", "es", "fr", "de", "it", "pt", "nl", "zh", "ja", "ko", "id", "tr", "ru"}
)


def build_turn_handling(language: str = "en", *, settings=None) -> dict:
    """面试与教练共用轮次设置：容纳思考停顿，确认回答结束后才生成响应。

    支持的语言使用语义检测，其余采用较长静音窗口；中日文提高打断字数门槛。
    """
    min_delay = getattr(settings, "interview_min_endpointing_delay_sec", 5.0)
    max_delay = getattr(settings, "interview_max_endpointing_delay_sec", 10.0)
    handling: dict = {
        "interruption": {
            # SDK 将中日文字符计作词，提高门槛以免短回应或回声打断题目。
            "min_words": 6 if language in {"zh", "ja"} else 3,
            "min_duration": 1.0,
            "resume_false_interruption": True,
            "false_interruption_timeout": 2.0,
        },
        "endpointing": {"mode": "dynamic", "min_delay": min_delay, "max_delay": max_delay},
        "preemptive_generation": {"enabled": False},
    }
    if language in _EOU_MODEL_LANGS:
        try:
            from livekit.plugins.turn_detector.multilingual import (
                MultilingualModel,
            )

            handling["turn_detection"] = MultilingualModel()
            return handling
        except Exception:  # noqa: BLE001 - 可选语义模型失败时回退到静音检测
            log.warning("build_turn_handling: turn-detector unavailable; using endpointing")
    handling["endpointing"]["min_delay"] = min(max_delay, max(min_delay, 4.0))
    return handling


def build_room_options(settings, *, delete_room_on_close: bool = False):
    """构造房间输入输出配置；仅显式启用且使用 Cloud 地址时尝试加载 BVC。

    BVC 初始化失败时回退原始音频；文本立即发布，不等待音频同步。
    """
    from livekit.agents.voice.room_io import RoomOptions, TextOutputOptions

    # 缺少词级时间戳时音文估算可能滞后，立即发布文本可避免打断时截掉题尾。
    options = RoomOptions(
        text_output=TextOutputOptions(sync_transcription=False),
        delete_room_on_close=delete_room_on_close,
    )
    url = settings.livekit_url or ""
    if not settings.enable_bvc or "livekit.cloud" not in url:
        return options
    try:
        from livekit.agents.voice.room_io import AudioInputOptions
        from livekit.plugins import noise_cancellation

        options.audio_input = AudioInputOptions(noise_cancellation=noise_cancellation.BVC())
    except Exception:
        log.exception("build_room_options: BVC unavailable; using raw audio")
    return options


def build_conn_options(settings):
    """本地提供方使用配置的较长调用时限；仅 MiniMax 云端时只延长模型等待。

    其余云端组合返回 None 使用 SDK 默认值；限制重试次数以免故障时长时间卡住。
    """
    is_minimax = _provider(settings, "llm") == "minimax"
    has_local = any(
        _provider(settings, stage) in accepted
        for stage, accepted in (("llm", _LOCAL_LLM), ("stt", _LOCAL_STT), ("tts", _LOCAL_TTS))
    )
    if not is_minimax and not has_local:
        return None

    from livekit.agents import APIConnectOptions
    from livekit.agents.voice.agent_session import SessionConnectOptions

    if is_minimax and not has_local:
        # 仅延长 MiniMax 模型等待，语音识别和合成保留各自默认配置。
        return SessionConnectOptions(
            llm_conn_options=APIConnectOptions(timeout=30.0, max_retry=1)
        )
    opts = APIConnectOptions(timeout=settings.local_provider_timeout_sec, max_retry=1)
    log.info(
        "build_conn_options: local provider selected; per-request timeout %.0fs",
        settings.local_provider_timeout_sec,
    )
    return SessionConnectOptions(
        stt_conn_options=opts, llm_conn_options=opts, tts_conn_options=opts
    )


def build_vad(proc: JobProcess | None = None):
    """优先复用进程预热的 Silero VAD，缺失时按需加载。"""
    if proc is not None and "vad" in proc.userdata:
        return proc.userdata["vad"]
    from livekit.plugins import silero

    return silero.VAD.load(max_buffered_speech=300.0)


def prewarm(proc: JobProcess) -> None:
    """在分配任务前预热 VAD 及较慢的模块导入，避免阻塞实时事件循环。

    轮次检测模型需要任务执行器，留到 entrypoint 中构造。
    """
    from livekit.plugins import silero

    proc.userdata["vad"] = silero.VAD.load(max_buffered_speech=300.0)
    # 预热阶段只导入慢模块；任务执行器尚不存在，模型实例需在入口构造。
    try:
        import importlib

        importlib.import_module("livekit.plugins.turn_detector.multilingual")
        importlib.import_module("huggingface_hub.file_download")
    except Exception:
        log.exception("prewarm: turn-detector unavailable; using endpointing")


def _api_base(settings) -> str:
    """优先使用 AGENT_API_URL，未设置时访问同主机 API 端口。"""
    return (settings.agent_api_url or f"http://localhost:{settings.agent_api_port}").rstrip("/")


def _internal_headers(settings) -> dict[str, str]:
    """配置内部密钥时返回回写和评分接口所需的请求头。"""
    secret = getattr(settings, "internal_api_secret", None)
    return {"X-Internal-Secret": secret} if secret else {}


def _session_id_from_room(ctx: JobContext) -> str:
    """依次从显式派发任务元数据、房间元数据、房间名读取 session_id。

    JSON 元数据无效时继续回退，不让旧格式阻断会话定位。
    """
    job_metadata = getattr(getattr(ctx, "job", None), "metadata", None)
    if job_metadata:
        try:
            return RoomMetadata.model_validate_json(job_metadata).session_id
        except Exception as exc:  # noqa: BLE001 - 无效元数据继续回退
            log.warning("worker: bad job metadata, trying room metadata (%s)", exc)
    metadata = getattr(ctx.room, "metadata", None)
    if metadata:
        try:
            return RoomMetadata.model_validate_json(metadata).session_id
        except Exception as exc:  # noqa: BLE001 - 无效元数据继续回退
            log.warning("worker: bad room metadata, using room name (%s)", exc)
    return ctx.room.name


async def _load_context_via_api(session_id: str, settings) -> InterviewContext | None:
    """通过 API 读取准备上下文，因为工作进程与 API 的内存仓库不共享。

    配置 Supabase 时虽共享存储，仍优先以 API 的会话视图为准。
    """
    import httpx

    url = f"{_api_base(settings)}/api/session/{session_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)  # 此读取接口不要求内部密钥。
    except Exception:
        log.exception("worker: failed to reach %s", url)
        return None
    if resp.status_code != 200:
        log.error("worker: GET %s -> %s", url, resp.status_code)
        return None
    ctx_data = resp.json().get("context")
    if not ctx_data:
        log.error("worker: session %s has no ready context", session_id)
        return None
    return InterviewContext.model_validate(ctx_data)


async def _load_context_with_retry(session_id: str, settings, *, timeout_sec: float = 60.0) -> InterviewContext | None:
    """在截止时间内轮询上下文，允许候选人入场时准备流程尚未结束。"""
    import asyncio

    import httpx

    deadline = asyncio.get_event_loop().time() + timeout_sec
    attempt = 0
    while True:
        attempt += 1
        try:
            ctx = await _load_context_via_api(session_id, settings)
        except (httpx.HTTPError, ValueError, KeyError):
            ctx = None
        if ctx is not None:
            if attempt > 1:
                log.info("worker: context for %s ready after %d attempts", session_id, attempt)
            return ctx
        if asyncio.get_event_loop().time() >= deadline:
            return None
        await asyncio.sleep(2.0)


async def entrypoint(ctx: JobContext) -> None:
    """加载准备上下文并启动语音会话，注册最终回写、回答恢复及评分派发回调。"""
    settings = get_settings()
    init_observability(settings)
    deps = build_deps(settings)

    # 会话启动前检查必要配置，减少首轮才暴露的连接或密钥缺失。
    _require_live_providers(settings)

    await ctx.connect()
    session_id = _session_id_from_room(ctx)

    # 房间允许准备期间加入，需等待计划可用而非首次未就绪就退出。
    interview_ctx = await _load_context_with_retry(session_id, settings)
    if interview_ctx is None:
        log.error("worker: no InterviewContext for session %s; aborting", session_id)
        return

    userdata = InterviewUserdata(ctx=interview_ctx, session_id=session_id)

    # 按主语言选择识别与合成组件，使语音与提示词语言保持一致。
    lang_mode = interview_ctx.plan.language_mode

    # 追踪覆盖语音任务并在正常关闭时结束；事件仅记录轮次形态。
    _live_trace = start_trace(
        "live",
        session_id=session_id,
        metadata={
            "language": lang_mode.primary,
            "questions": len(interview_ctx.plan.questions),
        },
    )
    _live_trace.__enter__()
    add_event("live.start", {"questions": len(interview_ctx.plan.questions)})
    # 本地转写与会话共用预热 VAD，避免重复加载。
    vad = build_vad(ctx.proc)
    conn_options = build_conn_options(settings)
    session: AgentSession[InterviewUserdata] = AgentSession(
        userdata=userdata,
        stt=build_stt(settings, lang_mode.primary, lang_mode.mixed, vad=vad),
        llm=build_llm(settings),
        tts=build_tts(settings, lang_mode.primary),
        vad=vad,
        # 本地或 MiniMax 组合可覆盖调用时限；None 保留 SDK 默认配置。
        **({"conn_options": conn_options} if conn_options else {}),
        # 确认回答结束后再生成，避免保存或推进工具抢在候选人回答之前。
        turn_handling=build_turn_handling(lang_mode.primary, settings=settings),
    )

    # 持久化真实提交的转写和智能体发言，不使用模型提供的回答摘要代替原话。
    wire_transcript_capture(session, userdata)
    wire_audio_path_logging(ctx, session)

    director = Director(
        userdata, enable_adaptive=settings.enable_adaptive_difficulty
    )
    director.start()

    # 房间内独立限制时长及轮数，不依赖网页创建额度；会话启动后才运行。
    guard = SessionGuard(
        session,
        userdata,
        max_duration_sec=settings.max_interview_duration_sec,
        max_turns=settings.max_interview_turns,
        wrap_up_line=guard_wrap_up_line(lang_mode.primary),
        answer_grace_sec=settings.interview_answer_grace_sec,
    )

    # 收集各提供方用量，关闭时汇总，便于核对语音费用。
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        usage_collector.collect(ev.metrics)

    api_base = _api_base(settings)

    async def _persist_via_api(has_answers: bool) -> bool:
        """优先通过 API 回写，以更新默认内存模式下 API 所属的权威仓库。

        失败返回 False；直接仓库回写只在共享持久化存储下能更新同一会话。
        """
        import httpx

        payload = {
            "context": userdata.ctx.model_dump(),
            "transcript": userdata.transcript,
            "status": None if has_answers else "no_answers",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{api_base}/api/session/{session_id}/live-result",
                    json=payload,
                    headers=_internal_headers(settings),
                )
            return resp.status_code == 200
        except Exception:
            log.exception("worker: live-result POST failed for %s", session_id)
            return False

    async def _flush_checkpoint(context, transcript: list[dict]) -> None:
        """通过 API 保存非终态检查点，异常交给 flusher 重试。

        不设置终态；会话已有终态时，结果接口拒绝迟到写入。
        """
        import httpx

        payload = {
            "context": context.model_dump(),
            "transcript": transcript,
            "status": None,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{api_base}/api/session/{session_id}/live-result",
                json=payload,
                headers=_internal_headers(settings),
            )
            resp.raise_for_status()

    flusher = TranscriptFlusher(
        userdata,
        _flush_checkpoint,
        interval_sec=settings.transcript_flush_interval_sec,
    )

    async def _persist_via_repo(has_answers: bool) -> bool:
        """直接仓库回写的兜底路径；只有两进程共享持久化存储时才更新同一会话。"""
        try:
            await deps.repo.save_transcript(session_id, userdata.transcript)
        except Exception:
            log.exception("worker: save_transcript failed for %s", session_id)
        try:
            await deps.repo.save_context(session_id, userdata.ctx)
        except Exception:
            log.exception(
                "worker: save_context FAILED for %s — answers not persisted; "
                "skipping scoring to avoid a blank scorecard",
                session_id,
            )
            # 标记 error，避免上下文写入失败后误报零分。
            try:
                await deps.repo.update_status(session_id, "error")
            except Exception:
                log.exception("worker: update_status(error) failed for %s", session_id)
            return False
        if not has_answers:
            try:
                await deps.repo.update_status(session_id, "no_answers")
            except Exception:
                log.exception("worker: update_status(no_answers) failed for %s", session_id)
        return True

    async def _on_shutdown() -> None:
        # 先结束追踪，便于任务收尾时读取完整事件。
        """先停止检查点，再恢复有效回答并回写；成功且有回答时才请求后台评分。"""
        try:
            add_event(
                "live.end",
                {
                    "turns": len(userdata.transcript),
                    "answers": len(
                        [a for a in userdata.ctx.answers if (a.transcript or "").strip()]
                    ),
                },
            )
        finally:
            # 关闭回调可能位于不同异步上下文，追踪清理失败不能阻断后续回写与评分。
            try:
                _live_trace.__exit__(None, None, None)
            except Exception:
                log.exception("worker: live trace close failed for %s; continuing", session_id)

        # 先停止检查点，避免中途快照与最终回写发生竞争。
        await flusher.aclose()
        await guard.aclose()
        await director.aclose()

        try:
            summary = usage_collector.get_summary()
            log.info("worker: session %s usage: %s", session_id, summary)
        except Exception:
            log.exception("worker: usage summary failed for %s", session_id)

        # 从原始转录恢复工具遗漏的有效回答，避免有实际发言却误判 no_answers。
        recovered = state.reconstruct_answers(userdata)
        if recovered:
            log.info(
                "worker: session %s recovered %d answer(s) from transcript",
                session_id,
                recovered,
            )

        # 仅非空回答触发评分，空记录不能改变无回答分支。
        has_answers = any((a.transcript or "").strip() for a in userdata.ctx.answers)

        # 先确认上下文回写成功再触发评分，否则评分会读到准备阶段的无回答状态。
        persisted = await _persist_via_api(has_answers)
        if not persisted:
            persisted = await _persist_via_repo(has_answers)
        if not persisted or not has_answers:
            if not has_answers:
                log.info("worker: session %s has no answers; skipping scoring", session_id)
            return

        # 评分交给 API 后台执行，避免完整评分耗尽工作进程关闭时限。
        try:
            import httpx

            req = ScoreRequest(session_id=session_id)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{api_base}/api/score/start",
                    json=req.model_dump(),
                    headers=_internal_headers(settings),
                )
                resp.raise_for_status()
        except Exception:
            log.exception("worker: scoring trigger failed for %s", session_id)

    ctx.add_shutdown_callback(_on_shutdown)

    @session.on("close")
    def _finish_job(ev) -> None:
        # 仅关闭语音会话不会立即退出任务，显式结束任务以触发回写和评分。
        ctx.shutdown(reason=f"interview session closed: {getattr(ev, 'reason', 'finished')}")

    room_options = build_room_options(settings, delete_room_on_close=True)
    start_kwargs = {"room_options": room_options} if room_options is not None else {}
    await session.start(
        agent=Interviewer(userdata),
        room=ctx.room,
        **start_kwargs,
    )

    # 会话启动后才启动限制检查，因为收尾需要调用会话的播报和关闭接口。
    guard.start()
    # 后台检查点减少硬退出损失；连续回写失败时仍可能丢失多个间隔的内容。
    flusher.start()


def main() -> None:
    # 显式将 Settings 中的 .env 凭据传入 SDK。
    settings = get_settings()
    init_observability(settings)
    # 在父进程构造选项前注册推理模块，避免子任务找不到轮次检测执行器。
    try:
        import importlib

        importlib.import_module("livekit.plugins.turn_detector.multilingual")
    except ImportError:
        log.warning("worker: turn-detector unavailable; using endpointing")
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            # 派发名称须与网页 roomConfig.agents 中一致，房间任务才能分配给此工作进程。
            agent_name=getattr(settings, "livekit_agent_name", None)
            or "intervyn-interviewer",
            # 最终回写和评分派发需足够关闭时间，避免工作进程被提前终止。
            shutdown_process_timeout=settings.shutdown_process_timeout_sec,
        )
    )


if __name__ == "__main__":
    main()
