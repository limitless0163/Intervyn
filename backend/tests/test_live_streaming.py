"""在 LiveKit 流式边界联合验证发问截断、追问等待及工具推进。"""

import asyncio

import pytest

pytest.importorskip("livekit.agents")

from livekit.agents import Agent, StopResponse, llm

from app.services.live import state

from .test_interview_progression import _agent


def _text(chunks):
    return "".join(
        chunk if isinstance(chunk, str) else chunk.delta.content or ""
        for chunk in chunks
        if isinstance(chunk, str) or chunk.delta
    )


@pytest.mark.parametrize("punctuation", ["?", "？"])
@pytest.mark.parametrize("structured", [False, True])
def test_first_spoken_question_stops_output_at_every_chunk_boundary(
    monkeypatch, punctuation, structured
):
    agent, context = _agent(monkeypatch)
    raw = f"<think>Should I advance?</think>How did you verify it{punctuation} Next question?"

    async def run():
        for boundary in range(len(raw) + 1):
            async def source(*args, split=boundary):
                for fragment in [raw[:split], raw[split:]]:
                    if structured:
                        yield llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content=fragment))
                    else:
                        yield fragment

            monkeypatch.setattr(Agent.default, "llm_node", source)
            chunks = [chunk async for chunk in agent.llm_node(None, [], None)]
            assert _text(chunks) == f"How did you verify it{punctuation}"
            # 首题尚无候选人回答，不能误标记为追问。
            assert not state.followup_is_pending(context.userdata)

    asyncio.run(run())


def test_streamed_followup_blocks_tools_from_the_same_response(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ledger.")
    tool = llm.FunctionToolCall(name="save_answer", arguments="{}", call_id="save-1")
    usage = llm.CompletionUsage(completion_tokens=4, prompt_tokens=6, total_tokens=10)
    original = llm.ChatChunk(
        id="reply",
        delta=llm.ChoiceDelta(
            content="What about retries? Next planned question?",
            tool_calls=[tool],
            extra={"signature": "preserved"},
        ),
    )

    async def source(*args):
        yield original
        assert state.followup_is_pending(ud)
        with pytest.raises(StopResponse):
            await agent.save_answer(context, "premature answer")
        with pytest.raises(StopResponse):
            await agent.get_next_question(context)
        yield "More questions must be suppressed?"
        yield llm.ChatChunk(id="reply", usage=usage)

    monkeypatch.setattr(Agent.default, "llm_node", source)

    async def run():
        return [chunk async for chunk in agent.llm_node(None, [], None)]

    chunks = asyncio.run(run())
    assert _text(chunks) == "What about retries?"
    assert chunks[0].delta.tool_calls == [tool]
    assert chunks[0].delta.extra == {"signature": "preserved"}
    assert chunks[-1].usage == usage
    assert original.delta.content == "What about retries? Next planned question?"
    assert ud.ctx.cursor == 0 and ud.ctx.answers == []


def test_answered_followup_requires_advance_before_next_spoken_question(monkeypatch):
    agent, context = _agent(monkeypatch)
    ud = context.userdata
    state.add_turn(ud, "user", "I built a ledger.")
    state.mark_followup_pending(ud)
    state.add_turn(ud, "user", "I used idempotency keys.")

    async def source(*args):
        yield "An extra follow-up must not be spoken?"
        await agent.save_answer(context, "ignored model summary")
        await agent.get_next_question(context)
        yield "Tell me about mentoring? And another question?"

    monkeypatch.setattr(Agent.default, "llm_node", source)

    async def run():
        return [chunk async for chunk in agent.llm_node(None, [], None)]

    chunks = asyncio.run(run())
    assert _text(chunks) == "Tell me about mentoring?"
    assert ud.ctx.cursor == 1
    assert ud.ctx.answers[-1].transcript == "I built a ledger. I used idempotency keys."
    assert not state.followup_is_pending(ud)
