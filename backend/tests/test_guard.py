"""Offline tests for the live SessionGuard (WP-5 cost/duration backstop).

The guard talks to the session through a tiny duck-typed surface (``say`` /
``shutdown``) and takes an injectable clock, so these run with a fake session
and a fake clock — no livekit, no real time.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.live.guard import SessionGuard


class _FakeSession:
    """Records the guard's say/shutdown calls."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.shutdown_called = False
        self.drain: bool | None = None

    async def say(self, text: str, **kwargs) -> None:
        self.said.append(text)

    async def interrupt(self) -> None:
        pass

    def shutdown(self, *, drain: bool = True) -> None:
        self.shutdown_called = True
        self.drain = drain


def _ud(turns: int = 0, session_id: str = "sess_test") -> SimpleNamespace:
    return SimpleNamespace(transcript=[{"role": "user", "text": "x"}] * turns, session_id=session_id)


async def _drive(guard: SessionGuard) -> None:
    """Start the guard and wait for its background task to finish."""
    guard.start()
    assert guard._task is not None
    await guard._task


def test_limit_reached_is_pure() -> None:
    guard = SessionGuard(_FakeSession(), _ud(), max_duration_sec=10, max_turns=3)
    assert guard._limit_reached(5.0) is None
    assert guard._limit_reached(10.0) is not None  # duration ceiling (>=)
    guard_turns = SessionGuard(_FakeSession(), _ud(turns=3), max_duration_sec=10_000, max_turns=3)
    assert guard_turns._limit_reached(0.0) is not None  # turn ceiling


def test_guard_trips_on_duration() -> None:
    session = _FakeSession()
    ticks = iter([0.0] + [100.0] * 10)  # start at 0, then elapsed >> max
    guard = SessionGuard(
        session, _ud(), max_duration_sec=10, max_turns=10_000,
        interval_sec=0.0, time_fn=lambda: next(ticks),
    )
    asyncio.run(_drive(guard))

    assert guard.tripped
    assert session.shutdown_called
    assert session.drain is True
    assert session.said


def test_duration_waits_for_unanswered_final_question() -> None:
    from app.services.live import state

    q = SimpleNamespace(id="last", section="wrap")
    ud = state.InterviewUserdata(
        ctx=SimpleNamespace(cursor=0, plan=SimpleNamespace(questions=[q]), answers=[]),
        session_id="sess_test",
    )
    session = _FakeSession()
    guard = SessionGuard(session, ud, max_duration_sec=10, max_turns=80,
                         interval_sec=0.001, time_fn=lambda: 10.0)

    async def run() -> None:
        guard._started_at = 0.0
        guard._task = asyncio.create_task(guard._run())
        await asyncio.sleep(0.01)
        assert ud.time_limit_reached
        assert not session.said
        assert not session.shutdown_called
        state.add_turn(ud, "user", "我可以每周到岗四天并且连续实习三个月。")
        state.save_answer(ud, transcript=state.spoken_answer(ud), started_at="", ended_at="")
        await guard._task

    asyncio.run(run())
    assert session.shutdown_called


def test_answer_grace_is_bounded_even_if_candidate_never_answers() -> None:
    ud = _ud()
    ud.ctx = SimpleNamespace(cursor=0, plan=SimpleNamespace(questions=[SimpleNamespace(id="q")]),
                             answers=[])
    session = _FakeSession()
    ticks = iter([0.0, 10.0, 310.0])
    guard = SessionGuard(session, ud, max_duration_sec=10, max_turns=80,
                         interval_sec=0.0, time_fn=lambda: next(ticks))
    asyncio.run(_drive(guard))
    assert guard.tripped and session.shutdown_called
    assert session.drain is True
    assert session.said, "guard should say a closing line before shutting down"


def test_guard_trips_on_turns() -> None:
    session = _FakeSession()
    guard = SessionGuard(
        session, _ud(turns=5), max_duration_sec=10_000, max_turns=5,
        interval_sec=0.0, time_fn=lambda: 0.0,
    )
    asyncio.run(_drive(guard))

    assert guard.tripped
    assert session.shutdown_called


def test_guard_does_not_trip_under_limits_and_closes_cleanly() -> None:
    session = _FakeSession()
    guard = SessionGuard(
        session, _ud(), max_duration_sec=10_000, max_turns=10_000,
        interval_sec=0.01, time_fn=lambda: 0.0,
    )

    async def _scenario() -> None:
        guard.start()
        await asyncio.sleep(0.0)  # let one iteration run (then it sleeps)
        await guard.aclose()  # cancel cleanly

    asyncio.run(_scenario())

    assert not guard.tripped
    assert not session.shutdown_called
    assert not session.said


def test_wrap_up_is_best_effort_when_session_raises() -> None:
    """A session whose say()/shutdown() raise must not crash the guard."""

    class _AngrySession:
        async def say(self, text: str) -> None:
            raise RuntimeError("say failed")

        def shutdown(self, *, drain: bool = True) -> None:
            raise RuntimeError("shutdown failed")

    guard = SessionGuard(
        _AngrySession(), _ud(), max_duration_sec=0, max_turns=10_000,
        interval_sec=0.0, time_fn=lambda: 0.0,
    )
    # Should complete without propagating the session's exceptions.
    asyncio.run(_drive(guard))
    assert guard.tripped
