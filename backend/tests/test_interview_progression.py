"""Live tool regressions: a question needs a real answer before advancing."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("livekit.agents")

from livekit.agents import StopResponse

from app.services.live import state
from app.services.live.interviewer import Interviewer

from .test_live import _userdata_two_sections


def _agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.prep.nodes.extract_cv_text",
        AsyncMock(return_value=("Backend engineer with data quality and pipeline experience.", [])),
    )
    ud = _userdata_two_sections()
    fake_session = SimpleNamespace(
        userdata=ud, user_state="listening", shutdown=lambda **kwargs: None
    )
    monkeypatch.setattr(Interviewer, "session", property(lambda self: fake_session))
    agent = Interviewer(ud)
    monkeypatch.setattr(agent, "_refresh_instructions", AsyncMock())
    return agent, SimpleNamespace(userdata=ud, session=fake_session)


def test_unanswered_question_cannot_advance_skip_or_end(monkeypatch):
    agent, context = _agent(monkeypatch)

    async def run():
        assert "WAIT" in await agent.get_next_question(context)
        await agent.next_section(context)
        await agent.end_interview(context)
        await agent.save_answer(context, "invented by the model")

    asyncio.run(run())
    assert context.userdata.ctx.cursor == 0
    assert context.userdata.ctx.answers == []
    assert not context.userdata.closing


def test_save_uses_real_speech_and_duplicate_advance_waits(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    actual = "我先核对数据采集链路，再检查指标口径和上游任务的延迟。"
    state.add_turn(ud, "user", actual)

    async def run():
        await agent.save_answer(context, "a misleading model summary")
        assert ud.ctx.answers[0].transcript == actual
        result = await agent.get_next_question(context)
        assert "STOP and WAIT" in result
        assert ud.ctx.cursor == 1
        await agent.get_next_question(context)
        await agent.end_interview(context)
        assert ud.ctx.cursor == 1
        assert not ud.closing
        state.add_turn(ud, "user", "这是第二个问题的回答。")
        await agent.save_answer(context, "ignored")
        assert "INTERVIEW_COMPLETE" in await agent.get_next_question(context)
        await agent.end_interview(context)
        assert ud.closing

    asyncio.run(run())


def test_budget_expiry_finishes_answer_before_wrap_without_new_question(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    ud.time_limit_reached = True

    async def run():
        await agent.get_next_question(context)
        assert ud.ctx.cursor == 0
        state.add_turn(ud, "user", "我会先排查数据源和任务运行状态，核对昨天和今天的指标口径。")
        await agent.save_answer(context, "ignored")
        assert "INTERVIEW_COMPLETE" in await agent.get_next_question(context)
        assert state.is_complete(ud)

    asyncio.run(run())


@pytest.mark.parametrize("tool", ["save_answer", "get_next_question", "next_section", "end_interview"])
def test_resumed_speech_blocks_pending_progression(monkeypatch, tool):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "我先核对数据源和指标口径，还有几个排查步骤需要补充。")
    state.save_answer(ud, transcript=state.spoken_answer(ud), started_at="", ended_at="")
    before = ud.ctx.model_dump()
    context.session.user_state = "speaking"

    async def run():
        with pytest.raises(StopResponse):
            if tool == "save_answer":
                await agent.save_answer(context, "premature summary")
            else:
                await getattr(agent, tool)(context)

    asyncio.run(run())
    assert ud.ctx.model_dump() == before
    assert not ud.closing


@pytest.mark.parametrize("tool", ["save_answer", "get_next_question", "next_section", "end_interview"])
def test_unanswered_followup_blocks_tools_even_with_saved_original_answer(monkeypatch, tool):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ledger and tested the retry path.")
    state.save_answer(ud, transcript=state.spoken_answer(ud), started_at="", ended_at="")
    state.mark_followup_pending(ud)
    before = ud.ctx.model_dump()

    async def run():
        with pytest.raises(StopResponse):
            if tool == "save_answer":
                await agent.save_answer(context, "premature summary")
            else:
                await getattr(agent, tool)(context)

    asyncio.run(run())
    assert ud.ctx.model_dump() == before
    assert not ud.closing


@pytest.mark.parametrize("budget_expired", [False, True])
def test_followup_reply_is_saved_verbatim_before_progression(monkeypatch, budget_expired):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    ud.time_limit_reached = budget_expired
    original = "I built a payments ledger."
    reply = "I used idempotency keys to prevent duplicate charges."
    state.add_turn(ud, "user", original)
    state.mark_followup_pending(ud)
    state.add_turn(ud, "assistant", "How did you prevent duplicates?")

    async def run():
        with pytest.raises(StopResponse):
            await agent.get_next_question(context)
        state.add_turn(ud, "user", reply)
        await agent.save_answer(context, "model summary must be ignored")
        result = await agent.get_next_question(context)
        assert ("INTERVIEW_COMPLETE" in result) == budget_expired

    asyncio.run(run())
    assert ud.ctx.answers[-1].transcript == f"{original} {reply}"
    assert ud.ctx.cursor == (len(ud.ctx.plan.questions) if budget_expired else 1)


def test_resumed_answer_can_be_saved_and_advanced_after_speech_finishes(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "我先检查数据源和任务状态。")
    context.session.user_state = "speaking"

    async def run():
        with pytest.raises(StopResponse):
            await agent.save_answer(context, "too early")
        assert ud.ctx.answers == []
        state.add_turn(ud, "user", "然后比较指标口径，验证上游数据是否完整。")
        context.session.user_state = "listening"
        await agent.save_answer(context, "ignored")
        assert "验证上游数据是否完整" in ud.ctx.answers[0].transcript
        assert "Next question" in await agent.get_next_question(context)

    asyncio.run(run())
