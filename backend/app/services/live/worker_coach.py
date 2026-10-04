"""语音学习教练工作进程，需安装 livekit 扩展并配置 LiveKit 及语音提供方。

运行：python -m app.services.live.worker_coach dev（生产模式为 start）。
复用面试工作进程的组件工厂，读取既有评分卡；教练转录单独保存，实时路径不接入检索。
"""

from __future__ import annotations

from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)

from ...core.config import get_settings
from ...core.logging import get_logger
from ...core.observability import init_observability
from ...core.tracing import add_event, start_trace
from ...dependencies.container import build_deps
from .coach_agent import CoachAgent
from .guard import SessionGuard
from .state import InterviewUserdata, weak_areas_summary

# 复用面试工作进程的组件与上下文加载逻辑，避免两条语音路径配置漂移。
from .worker import (
    _load_context_via_api,
    _session_id_from_room,
    build_conn_options,
    build_llm,
    build_room_options,
    build_stt,
    build_tts,
    build_turn_handling,
    build_vad,
    wire_transcript_capture,
)

log = get_logger(__name__)


async def entrypoint(ctx: JobContext) -> None:
    """复用会话的评分摘要启动语音教练，关闭时只写独立教练转录。"""
    settings = get_settings()
    init_observability(settings)
    deps = build_deps(settings)

    await ctx.connect()
    session_id = _session_id_from_room(ctx)

    interview_ctx = await _load_context_via_api(session_id, settings)
    if interview_ctx is None:
        log.error("worker_coach: no InterviewContext for session %s; aborting", session_id)
        return

    primary = interview_ctx.plan.language_mode.primary
    summary = weak_areas_summary(interview_ctx.scorecard)

    # 复用面试会话行，但教练发言写入独立的 coach_transcript，避免覆盖面试记录。
    userdata = InterviewUserdata(ctx=interview_ctx, session_id=session_id)

    # 记录教练会话追踪，关闭时结束。
    _coach_trace = start_trace("coach", session_id=session_id, metadata={"language": primary})
    _coach_trace.__enter__()
    add_event("coach.start", {})

    # 本地 Whisper 转写与会话共用 VAD。
    vad = build_vad()
    conn_options = build_conn_options(settings)
    session: AgentSession[InterviewUserdata] = AgentSession(
        userdata=userdata,
        stt=build_stt(settings, primary, vad=vad),
        llm=build_llm(settings),
        tts=build_tts(settings, primary),
        vad=vad,
        turn_handling=build_turn_handling(primary, settings=settings),
        # 本地提供方使用更长调用时限，None 表示保留 SDK 默认值。
        **({"conn_options": conn_options} if conn_options else {}),
    )

    # 监听真实教练发言；不标注面试题号，因为教练对话不属于面试答题。
    wire_transcript_capture(session, userdata, tag_questions=False)

    # 教练对话也使用时长及轮数限制，避免计费语音会话无限运行。
    guard = SessionGuard(
        session,
        userdata,
        max_duration_sec=settings.max_interview_duration_sec,
        max_turns=settings.max_interview_turns,
    )

    async def _on_shutdown() -> None:
        try:
            add_event("coach.end", {"turns": len(userdata.transcript)})
        finally:
            _coach_trace.__exit__(None, None, None)
        await guard.aclose()
        if not userdata.transcript:
            return
        try:
            await deps.repo.save_coach_transcript(session_id, userdata.transcript)
        except Exception:
            log.exception("worker_coach: save_coach_transcript failed for %s", session_id)

    ctx.add_shutdown_callback(_on_shutdown)

    room_options = build_room_options(settings)
    start_kwargs = {"room_options": room_options} if room_options is not None else {}
    await session.start(
        agent=CoachAgent(
            weak_areas_summary=summary,
            lang=primary,
        ),
        room=ctx.room,
        **start_kwargs,
    )

    guard.start()


def main() -> None:
    # SDK 从环境读取凭据，此处显式传入 Settings 值，使 .env 配置也能生效。
    settings = get_settings()
    init_observability(settings)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )


if __name__ == "__main__":
    main()
