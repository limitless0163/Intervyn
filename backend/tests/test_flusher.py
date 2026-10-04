"""以注入的保存函数直接验证检查点增长检测和失败重试，不联网或真实等待。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.live.flusher import TranscriptFlusher


def _userdata(transcript: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(transcript=transcript, ctx=SimpleNamespace(name="ctx"))


def test_checkpoint_flushes_only_when_transcript_grows() -> None:
    calls: list[int] = []

    async def flush(ctx, transcript: list[dict]) -> None:
        calls.append(len(transcript))

    transcript: list[dict] = []
    ud = _userdata(transcript)
    flusher = TranscriptFlusher(ud, flush, interval_sec=5.0)

    asyncio.run(flusher._checkpoint())
    assert calls == []

    transcript.append({"role": "user", "text": "hi"})
    asyncio.run(flusher._checkpoint())
    assert calls == [1]

    asyncio.run(flusher._checkpoint())
    assert calls == [1]

    transcript.append({"role": "agent", "text": "welcome"})
    asyncio.run(flusher._checkpoint())
    assert calls == [1, 2]


def test_checkpoint_swallows_flush_errors_and_retries_next_tick(caplog) -> None:
    attempts: list[int] = []

    async def flaky(ctx, transcript: list[dict]) -> None:
        attempts.append(len(transcript))
        raise RuntimeError("api down")

    transcript = [{"role": "user", "text": "one"}]
    ud = _userdata(transcript)
    flusher = TranscriptFlusher(ud, flaky, interval_sec=5.0)

    # 保存失败不能推进水位，下次相同快照必须继续重试。
    asyncio.run(flusher._checkpoint())
    asyncio.run(flusher._checkpoint())
    assert attempts == [1, 1]
    assert "checkpoint failed; will retry" in caplog.text
    assert "api down" in caplog.text


def test_checkpoint_isolated_from_turn_mutations_during_network_wait():
    turns = [{"role": "user", "text": "snapshot"}]
    captured = []

    async def flush(ctx, transcript):
        turns[0]["text"] = "changed while saving"
        captured.extend(transcript)

    flusher = TranscriptFlusher(_userdata(turns), flush)
    asyncio.run(flusher._checkpoint())
    assert captured[0]["text"] == "snapshot"


def test_start_is_noop_when_interval_non_positive() -> None:
    async def flush(ctx, transcript: list[dict]) -> None: ...

    flusher = TranscriptFlusher(_userdata([]), flush, interval_sec=0.0)

    async def run() -> None:
        flusher.start()
        assert flusher._task is None
        await flusher.aclose()

    asyncio.run(run())


def test_start_then_aclose_cancels_the_task() -> None:
    async def flush(ctx, transcript: list[dict]) -> None: ...

    async def run() -> None:
        flusher = TranscriptFlusher(_userdata([]), flush, interval_sec=30.0)
        flusher.start()
        assert flusher._task is not None
        await flusher.aclose()
        assert flusher._task is None

    asyncio.run(run())
