"""模型仅致谢时完成轮次，同时保留真实发言、追问和打断边界。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("livekit.agents")

from livekit.agents import Agent, AgentSession, llm
from livekit.plugins import openai

from app.services.live import state
from app.services.live.interviewer import Interviewer
from app.services.live.worker import wire_transcript_capture

from .test_interview_progression import _agent
from .test_live_streaming import _text


def _source(monkeypatch, fragments, *, structured=False):
    async def source(*args):
        for fragment in fragments:
            if structured:
                yield llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content=fragment))
            else:
                yield fragment

    monkeypatch.setattr(Agent.default, "llm_node", source)


def _run(agent):
    async def run():
        return [chunk async for chunk in agent.llm_node(None, [], None)]

    return asyncio.run(run())


@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("reply", ["谢谢你，介绍得很全面。", "Thank you for your answer.", ""])
def test_acknowledgement_saves_actual_answer_and_speaks_next_question(
    monkeypatch, structured, reply
):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    actual = "我有使用 PyTorch 进行模型训练、优化和部署的经验，也做过推荐系统项目。"
    state.add_turn(ud, "user", actual)
    next_question = ud.ctx.plan.questions[1].text["en"]
    _source(monkeypatch, list(reply), structured=structured)

    chunks = _run(agent)

    assert _text(chunks) == reply + " " + next_question
    assert ud.ctx.cursor == 1
    assert len(ud.ctx.answers) == 1
    assert ud.ctx.answers[0].transcript == actual
    assert not state.followup_is_pending(ud)
    agent._refresh_instructions.assert_awaited_once_with(ud)


@pytest.mark.parametrize("blocked", ["speaking", "interrupted", "closing", "followup", "thinking"])
def test_acknowledgement_does_not_advance_when_candidate_must_be_allowed_to_finish(
    monkeypatch, blocked
):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "我做过推荐系统项目。")
    if blocked == "speaking":
        context.session.user_state = "speaking"
    elif blocked == "interrupted":
        context.session.current_speech = SimpleNamespace(interrupted=True)
    elif blocked == "closing":
        ud.closing = True
    elif blocked == "followup":
        state.mark_followup_pending(ud)
    else:
        state.add_turn(ud, "user", "让我想想，我还没说完。")
    _source(monkeypatch, ["好的。"])

    assert _text(_run(agent)) == ("" if blocked == "followup" else "好的。")
    assert ud.ctx.cursor == 0
    assert ud.ctx.answers == []


@pytest.mark.parametrize("reply", ["请介绍一下你的项目。", "Tell me about that project.", "Why?"])
def test_substantive_followup_is_not_treated_as_an_acknowledgement(monkeypatch, reply):
    agent, context = _agent(monkeypatch)
    state.add_turn(context.userdata, "user", "I built a ranking system.")
    _source(monkeypatch, [reply])

    assert _text(_run(agent)) == reply
    assert context.userdata.ctx.cursor == 0
    assert context.userdata.ctx.answers == []


def test_tool_call_without_text_defers_to_sdk_instead_of_racing_progression(monkeypatch):
    agent, context = _agent(monkeypatch)
    state.add_turn(context.userdata, "user", "I built a ranking system.")
    tool = llm.FunctionToolCall(name="save_answer", arguments="{}", call_id="save-1")

    async def source(*args):
        yield "Thanks."
        yield llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(tool_calls=[tool]))

    monkeypatch.setattr(Agent.default, "llm_node", source)
    chunks = _run(agent)
    assert _text(chunks) == "Thanks."
    assert chunks[-1].delta.tool_calls == [tool]
    assert context.userdata.ctx.cursor == 0
    assert context.userdata.ctx.answers == []


def test_candidate_resuming_during_generation_prevents_recovery(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ranking system.")

    async def source(*args):
        yield "Thanks."
        state.add_turn(ud, "user", "I also want to explain its evaluation.")

    monkeypatch.setattr(Agent.default, "llm_node", source)
    assert _text(_run(agent)) == "Thanks."
    assert ud.ctx.cursor == 0
    assert ud.ctx.answers == []


def test_acknowledgement_after_save_does_not_duplicate_answer(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ranking system.")
    asyncio.run(agent.save_answer(context, "ignored"))
    _source(monkeypatch, ["Thanks."])

    _run(agent)
    assert ud.ctx.cursor == 1
    assert len(ud.ctx.answers) == 1


def test_acknowledgement_after_advance_asks_current_question_without_skipping(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ranking system.")

    async def advance():
        await agent.save_answer(context, "ignored")
        await agent.get_next_question(context)

    asyncio.run(advance())
    _source(monkeypatch, ["Thanks."])

    assert _text(_run(agent)) == "Thanks. " + state.current_question(ud).text["en"]
    assert ud.ctx.cursor == 1
    assert len(ud.ctx.answers) == 1


def test_answered_followup_with_missing_tools_is_saved_before_next_question(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ranking system.")
    asyncio.run(agent.save_answer(context, "ignored"))
    state.mark_followup_pending(ud)
    state.add_turn(ud, "user", "I used AUC and online experiments to evaluate it.")
    _source(monkeypatch, ["Thanks."])

    assert _text(_run(agent)) == " " + ud.ctx.plan.questions[1].text["en"]
    assert ud.ctx.cursor == 1
    assert ud.ctx.answers[-1].transcript == (
        "I built a ranking system. I used AUC and online experiments to evaluate it."
    )


@pytest.mark.parametrize("budget_expired", [False, True])
def test_last_answer_or_time_limit_speaks_wrapup_and_drains_session(monkeypatch, budget_expired):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    ud.ctx.plan.language_mode.primary = "zh"
    if budget_expired:
        ud.time_limit_reached = True
    else:
        ud.ctx.cursor = len(ud.ctx.plan.questions) - 1
    state.add_turn(ud, "user", "我会主动向同事征求反馈，并通过明确的行动项进行改进。")
    context.session.shutdown = Mock()
    _source(monkeypatch, ["谢谢你。"])

    text = _text(_run(agent))
    assert "反馈报告" in text
    assert ("时间已到" in text) == budget_expired
    assert ud.ctx.cursor == len(ud.ctx.plan.questions)
    assert len(ud.ctx.answers) == 1
    assert ud.closing
    context.session.shutdown.assert_called_once_with(drain=True)


def test_generation_failure_does_not_save_or_advance(monkeypatch):
    agent, context = _agent(monkeypatch)
    state.add_turn(context.userdata, "user", "I built a ranking system.")

    async def source(*args):
        yield "Thanks."
        raise RuntimeError("provider failed")

    monkeypatch.setattr(Agent.default, "llm_node", source)
    with pytest.raises(RuntimeError, match="provider failed"):
        _run(agent)
    assert context.userdata.ctx.cursor == 0
    assert context.userdata.ctx.answers == []


@pytest.mark.parametrize("last_question", [False, True])
def test_real_sdk_commits_completed_reply_before_session_closes(monkeypatch, last_question):
    original_session_property = Interviewer.session
    _, context = _agent(monkeypatch)
    ud = context.userdata
    ud.ctx.plan.language_mode.primary = "zh"
    ud.ctx.plan.questions[0].text = {"zh": "请介绍你的背景。"}
    ud.ctx.plan.questions[1].text = {"zh": "请分享一次模型上线后解决生产问题的经历。"}
    if last_question:
        ud.ctx.cursor = len(ud.ctx.plan.questions) - 1
    monkeypatch.setattr(Interviewer, "session", original_session_property)
    monkeypatch.setattr(Interviewer, "on_enter", AsyncMock())
    _source(monkeypatch, list("谢谢你，介绍得很全面。"), structured=True)

    async def run():
        # 模型节点已被离线流替换，但保留 SDK 的生成、历史、关闭和事件管道。
        async with AgentSession(
            userdata=ud,
            llm=openai.LLM(api_key="test"),
            turn_handling={"turn_detection": "manual"},
            user_away_timeout=None,
        ) as session:
            closed = asyncio.Event()
            session.on("close", lambda ev: closed.set())
            wire_transcript_capture(session, ud)
            await session.start(agent=Interviewer(ud))
            await asyncio.wait_for(
                session.run(user_input="我有模型训练和部署经验，也做过推荐系统项目。"),
                timeout=5.0,
            )
            if last_question:
                await asyncio.wait_for(closed.wait(), timeout=5.0)
            else:
                assert not closed.is_set()

    asyncio.run(run())
    assert len(ud.ctx.answers) == 1
    assert ud.ctx.answers[0].transcript == "我有模型训练和部署经验，也做过推荐系统项目。"
    assert ud.ctx.cursor == (len(ud.ctx.plan.questions) if last_question else 1)
    committed = ud.transcript[-1]
    assert committed["role"] == "assistant"
    assert committed["text"].startswith("谢谢你，介绍得很全面。")
    assert ("反馈报告" in committed["text"]) == last_question
    if not last_question:
        assert state.current_question(ud).text["zh"] in committed["text"]
