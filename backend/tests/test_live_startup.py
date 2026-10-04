"""回归 MiniMax 开场消息和 LiveKit 转写配置导致的静默启动问题。"""

from types import SimpleNamespace

import pytest

pytest.importorskip("livekit.agents")

from livekit.agents import inference, llm
from livekit.plugins import openai

from app.services.live.minimax_llm import MiniMaxLLM
from app.services.live.worker import build_llm, build_stt, build_tts


@pytest.mark.parametrize("has_user", [False, True])
def test_minimax_opener_adds_request_only_message(monkeypatch, has_user):
    ctx = llm.ChatContext()
    ctx.add_message(role="system", content="Greet the candidate and ask Q1.")
    if has_user:
        ctx.add_message(role="user", content="My actual answer.")
    original = list(ctx.items)
    captured = {}

    def chat(self, **kwargs):
        captured.update(kwargs)
        return "stream"

    monkeypatch.setattr(openai.LLM, "chat", chat)
    model = MiniMaxLLM(model="test", api_key="test")
    assert model.chat(chat_ctx=ctx, tools=[]) == "stream"
    assert ctx.items == original  # 补充请求消息不能成为候选人原话或评分依据。
    outgoing = captured["chat_ctx"]
    assert any(item.role == "user" for item in outgoing.items)
    if has_user:
        assert outgoing is ctx
    else:
        assert len(outgoing.items) == len(original) + 1
    assert captured["tools"] == []
    assert captured["parallel_tool_calls"] is False


def test_minimax_factory_uses_compatible_opener():
    model = build_llm(
        SimpleNamespace(
            llm_provider="minimax",
            minimax_api_key="test",
            minimax_model="test",
            minimax_model_live="live-test",
            minimax_base_url="https://example.com",
        )
    )
    assert isinstance(model, MiniMaxLLM)
    assert model.model == "live-test"


def test_minimax_tts_uses_pcm_for_multi_sentence_streams():
    tts = build_tts(
        SimpleNamespace(
            tts_provider="minimax",
            minimax_api_key="test",
            minimax_base_url="https://example.com",
            minimax_tts_model="speech-2.8-turbo",
            minimax_tts_voice="socialmedia_female_2_v1",
        )
    )
    assert tts._opts.audio_format == "pcm"


@pytest.mark.parametrize("mixed", [False, True])
def test_livekit_stt_uses_inference_gateway(monkeypatch, mixed):
    monkeypatch.delenv("LIVEKIT_INFERENCE_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    stt = build_stt(
        SimpleNamespace(
            stt_provider="livekit",
            livekit_stt_model="google/gemini-3.5-transcribe-live",
            livekit_url="wss://room.example.livekit.cloud",
            livekit_api_key="test",
            livekit_api_secret="test",
        ),
        language="zh",
        mixed=mixed,
    )
    assert isinstance(stt, inference.STT)
    assert stt._opts.base_url == "https://agent-gateway.livekit.cloud/v1"
    if mixed:
        assert not isinstance(stt._opts.language, str)
    else:
        assert stt._opts.language == "zh"


def test_captions_are_immediate_and_completed_interviews_close_room():
    from app.services.live.worker import build_room_options

    options = build_room_options(
        SimpleNamespace(enable_bvc=False, livekit_url="wss://test.livekit.cloud"),
        delete_room_on_close=True,
    )
    assert options.text_output.sync_transcription is False
    assert options.delete_room_on_close is True


def test_minimax_live_timeout_does_not_abort_at_ten_seconds():
    from app.services.live.worker import build_conn_options

    options = build_conn_options(SimpleNamespace(llm_provider="minimax"))
    assert options.llm_conn_options.timeout == 30.0
    assert options.llm_conn_options.max_retry == 1


def test_prewarm_does_not_construct_turn_detector_without_job_context(monkeypatch):
    from livekit.plugins import silero
    from livekit.plugins.turn_detector import multilingual

    from app.services.live.worker import prewarm

    monkeypatch.setattr(silero.VAD, "load", lambda **kwargs: "warmed-vad")
    monkeypatch.setattr(multilingual, "MultilingualModel",
                        lambda: pytest.fail("turn detector needs a running JobContext"))
    proc = SimpleNamespace(userdata={})
    prewarm(proc)
    assert proc.userdata["vad"] == "warmed-vad"
