"""使用实际语音 SDK 验证思考停顿设置及完整句子的合成分块。"""

import asyncio

import pytest
from pydantic import ValidationError

pytest.importorskip("livekit.agents")

from livekit.agents import AgentSession
from livekit.agents.voice.endpointing import DynamicEndpointing
from livekit.plugins.turn_detector import multilingual

from app.core.config import Settings
from app.services.live.worker import build_tts, build_turn_handling


def test_semantic_turn_handling_waits_longer_and_disables_speculation(monkeypatch):
    detector = object()
    monkeypatch.setattr(multilingual, "MultilingualModel", lambda: detector)
    handling = build_turn_handling("zh")
    assert handling["turn_detection"] is detector
    assert handling["endpointing"] == {"mode": "dynamic", "min_delay": 5.0, "max_delay": 10.0}
    assert handling["preemptive_generation"] == {"enabled": False}


@pytest.mark.parametrize("language", ["zh", "vi"])
def test_endpointing_fallback_preserves_thinking_pause(monkeypatch, language):
    def unavailable():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(multilingual, "MultilingualModel", unavailable)
    handling = build_turn_handling(language)
    assert "turn_detection" not in handling
    assert handling["endpointing"]["min_delay"] == 5.0
    assert handling["endpointing"]["max_delay"] == 10.0

    # 通过实际 SDK 解析配置，避免只检查字典却遗漏版本接口不兼容。
    async def run():
        session = AgentSession(turn_handling=handling)
        assert session.options.endpointing["mode"] == "dynamic"
        assert session.options.endpointing["min_delay"] == 5.0
        assert session.options.preemptive_generation["enabled"] is False
        await session.aclose()

    asyncio.run(run())


def test_dynamic_endpointing_learns_longer_pauses():
    endpointing = DynamicEndpointing(min_delay=5.0, max_delay=10.0)
    endpointing.on_start_of_speech(0.0)
    endpointing.on_end_of_speech(2.0)
    endpointing.on_start_of_speech(9.0)
    endpointing.on_end_of_speech(11.0)
    assert 5.0 < endpointing.min_delay <= 10.0


def test_endpointing_custom_bounds_and_invalid_settings(monkeypatch):
    settings = Settings(
        _env_file=None,
        interview_min_endpointing_delay_sec=3.0,
        interview_max_endpointing_delay_sec=3.5,
    )
    handling = build_turn_handling("vi", settings=settings)
    assert handling["endpointing"]["min_delay"] == 3.5
    assert handling["endpointing"]["max_delay"] == 3.5
    with pytest.raises(ValidationError):
        Settings(_env_file=None, interview_min_endpointing_delay_sec=11.0,
                 interview_max_endpointing_delay_sec=10.0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, minimax_tts_speed=2.1)


@pytest.mark.parametrize("language", ["zh", "en"])
def test_minimax_pacing_coalesces_short_sentences_without_losing_text(language):
    tts = build_tts(
        Settings(_env_file=None, tts_provider="minimax", minimax_api_key="test",
                 minimax_tts_speed=0.95),
        language,
    )
    assert tts._opts.speed == 0.95
    assert tts._opts.emotion == "neutral"
    assert tts._opts.text_normalization is True
    assert tts._opts.audio_format == "pcm"
    text = (
        "好的。我们接着聊。请结合你刚才描述的项目经历，说明如何验证数据的完整性，"
        "以及你会怎样定位上游任务延迟导致的指标异常。"
        if language == "zh" else
        "Thank you. Let's continue. Please describe how you validate data quality "
        "and investigate delayed upstream jobs in your most recent project."
    )

    async def run():
        stream = tts._sentence_tokenizer.stream()
        for char in text:
            stream.push_text(char)
        stream.end_input()
        chunks = [item.token async for item in stream]
        await stream.aclose()
        assert chunks
        assert len(chunks[0]) >= (50 if language == "zh" else 120)
        assert "".join("".join(chunks).split()) == "".join(text.split())

    asyncio.run(run())
