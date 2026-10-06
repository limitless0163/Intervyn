"""从环境变量及工作目录的 .env 读取配置；默认使用无需密钥的离线模拟提供方。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """提供方及运行配置；从进程环境和工作目录 .env 加载，忽略未知字段。"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 提供方默认使用离线模拟。
    llm_provider: str = "mock"
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    embeddings_provider: str = "mock"

    # 准备和评分采用后台模型；语音面试单独选择低延迟模型。
    gemini_model: str = "gemini-3.6-flash"
    # 固定模型 ID，避免别名升级改变工具调用行为；插件需保留 thought_signature。
    gemini_model_live: str = "gemini-3.5-flash-lite"
    # 用于 Cartesia 未覆盖语言的 Gemini 语音回退。
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    # 可用 OPENAI_MODEL 覆盖；启用前需确认部署账户可访问此型号。
    openai_model: str = "gpt-5.1-mini"
    # 同一密钥用于 MiniMax 模型及语音合成。
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.io"
    minimax_model: str = "MiniMax-M3"
    minimax_model_live: str = ""
    minimax_tts_model: str = "speech-2.8-turbo"
    minimax_tts_voice: str = "socialmedia_female_2_v1"
    minimax_tts_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    # 用于 Cartesia 未覆盖语言的多语言语音回退。
    elevenlabs_model: str = "eleven_flash_v2_5"

    # 本地 Ollama、Whisper 和 Kokoro 复用兼容 OpenAI 的接口，无需云端密钥。
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:8b"
    # 留空时复用准备模型，避免默认切换到本机尚未下载的小模型。
    ollama_model_live: str = ""
    whisper_base_url: str = "http://localhost:8000/v1"
    # 选择较轻的多语言模型，为并发推理留出转写超时余量。
    whisper_model: str = "Systran/faster-whisper-base"
    kokoro_base_url: str = "http://localhost:8880/v1"
    # tts-1 用于选择插件的音频字节分支；其他型号可能误入 SSE 分支导致无声。
    kokoro_model: str = "tts-1"
    # 留空时按会话语言选声音；Kokoro 声音 ID 的前缀决定语言。
    kokoro_voice: str = ""
    # PCM 按插件的 24 kHz 采样率解码；采样率不匹配会改变语速和音高。
    kokoro_response_format: str = "pcm"
    # 本地服务无需鉴权，但 SDK 要求显式传入非空占位密钥。
    local_api_key: str = "local"
    # 入场前探测本地服务，避免候选人开始面试后才遇到连接失败。
    local_probe_timeout_sec: float = Field(default=2.0, gt=0, allow_inf_nan=False)
    # 本地推理允许更长调用时限，以覆盖冷启动和共享算力下的延迟。
    local_provider_timeout_sec: float = Field(default=30.0, gt=0, allow_inf_nan=False)

    # 可选提供方密钥。
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    soniox_api_key: str | None = None
    deepgram_api_key: str | None = None
    cartesia_api_key: str | None = None
    elevenlabs_api_key: str | None = None

    # 可选 Supabase 持久化配置，地址和服务端密钥须同时设置。
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    # LiveKit 连接和工作进程派发配置。
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    livekit_stt_model: str = "google/gemini-3.5-transcribe-live"
    # 必须与网页令牌中的 roomConfig.agents[0].agentName 一致，否则房间无法派发智能体。
    livekit_agent_name: str = "intervyn-interviewer"

    # 未配置侧车地址时，知识适配器保持离线模拟。
    lightrag_url: str | None = None
    # 通过 X-Internal-Secret 发送，须与侧车配置的密钥一致。
    lightrag_api_secret: str | None = None

    # 配置后校验内部写入和计算接口；网页服务端及工作进程需携带同一密钥。
    internal_api_secret: str | None = None

    # 服务监听及工作进程回连配置。
    agent_api_port: int = Field(default=8000, ge=1, le=65535)
    # 工作进程访问 API 的地址；容器内应使用服务 DNS，不能用指向自身的 localhost。
    agent_api_url: str | None = None
    default_language: str = "en"

    # 提供方调用须有时限，才能在卡住时进入准备或评分的降级分支。
    llm_call_timeout_sec: float = Field(default=90.0, gt=0, allow_inf_nan=False)
    company_research_timeout_sec: float = Field(default=120.0, gt=0, allow_inf_nan=False)

    # 此开关控制后台难度观测；实时工具通过本地启发式给出建议，不等待模型评估。
    enable_adaptive_difficulty: bool = False

    # 对低分或边界分做二次核验；超时或失败时保留原评分。
    enable_score_verifier: bool = False
    score_verifier_timeout_sec: float = Field(default=60.0, gt=0, allow_inf_nan=False)

    # 仅在确认原生滤镜可加载的主机启用，初始化失败可能阻断输入音频。
    enable_bvc: bool = False

    # 端点延迟容纳面试中的思考停顿，衡量静音而非回答总时长。
    interview_min_endpointing_delay_sec: float = Field(default=5.0, ge=0.5, allow_inf_nan=False)
    interview_max_endpointing_delay_sec: float = Field(default=10.0, ge=0.5, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_endpointing_delays(self) -> Settings:
        if self.interview_max_endpointing_delay_sec < self.interview_min_endpointing_delay_sec:
            raise ValueError("Interview maximum endpointing delay must be >= minimum delay")
        return self

    # 达到时长或轮次上限后停止提新问题，当前回答仍有有限收尾宽限。
    max_interview_duration_sec: int = Field(default=2400, gt=0)
    max_interview_turns: int = Field(default=80, gt=0)
    interview_answer_grace_sec: float = Field(default=300.0, ge=0, allow_inf_nan=False)

    # 关闭回调需留足回写时间；周期检查点减少硬退出时的数据损失。
    # 检查点间隔设为 0 时关闭，异常退出仍可能丢失尚未回写的内容。
    shutdown_process_timeout_sec: float = Field(default=60.0, gt=0, allow_inf_nan=False)
    transcript_flush_interval_sec: float = Field(default=20.0, ge=0, allow_inf_nan=False)

    # 评分阶段各自限时，失败时生成有效降级结果，避免整份报告丢失。
    score_stage_timeout_sec: float = Field(default=60.0, gt=0, allow_inf_nan=False)
    # 启用后只向待审目录写入去标识化草稿，不能自动发布到正式技能库。
    enable_skill_distiller: bool = False

    # 本地 JSONL 追踪可通过 CLI 或 API 读取；TRACE_ENABLED=0 关闭。
    trace_enabled: bool = True
    trace_dir: str = ".intervyn/traces"
    # 仅显式开启时记录前 500 字符，预览仍可能包含敏感资料。
    trace_include_prompts: bool = False
    # 配置双密钥并安装 observability 扩展后，通过 OTel 同步到 Langfuse。
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    """缓存从环境变量和工作目录 .env 加载的配置。"""
    return Settings()
