"""验证流式推理内容不会进入字幕、语音或面试历史。"""

import asyncio
import json

import pytest

from app.services.live.reasoning import ReasoningFilter


@pytest.mark.parametrize("tag", ["think", "thinking", "THINK", "Thinking"])
def test_reasoning_stays_hidden_at_every_chunk_boundary(tag):
    raw = f"好的。<{tag}>Let me save and get next question.</{tag}>接下来聊聊项目。"
    for boundary in range(len(raw) + 1):
        parser = ReasoningFilter()
        output = parser.feed(raw[:boundary]) + parser.feed(raw[boundary:]) + parser.finish()
        assert output == "好的。接下来聊聊项目。"
    parser = ReasoningFilter()
    assert "".join(parser.feed(char) for char in raw) + parser.finish() == "好的。接下来聊聊项目。"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("<think>unfinished private notes", ""),
        ("好的。<thinking>unfinished", "好的。"),
        ("<think>outer<thinking>inner</thinking>outer</think>问题？", "问题？"),
        ("<think>first</think>Hi.<think>second</think>Question?", "Hi.Question?"),
        (
            "Tell me about your data engineering project with StarRocks and Iceberg.",
            "Tell me about your data engineering project with StarRocks and Iceberg.",
        ),
        (
            "x < 3; O(n); C++，Python，降低了 40% 的成本。",
            "x < 3; O(n); C++，Python，降低了 40% 的成本。",
        ),
        ("好的。<thi", "好的。"),
    ],
)
def test_reasoning_filter_preserves_answers_and_drops_unfinished_thoughts(raw, expected):
    parser = ReasoningFilter()
    assert parser.feed(raw) + parser.finish() == expected


def test_live_node_preserves_tools_usage_and_metadata(monkeypatch):
    pytest.importorskip("livekit.agents")
    from livekit.agents import Agent, llm

    from app.services.live.interviewer import Interviewer

    tool = llm.FunctionToolCall(
        name="save_answer", arguments='{"answer":"real answer"}', call_id="call-1"
    )
    usage = llm.CompletionUsage(completion_tokens=12, prompt_tokens=10, total_tokens=22)
    chunks = [
        llm.ChatChunk(id="1", delta=llm.ChoiceDelta(content="<thi")),
        llm.ChatChunk(
            id="1",
            delta=llm.ChoiceDelta(
                content="nking>Save first.", tool_calls=[tool], extra={"signature": "keep"}
            ),
        ),
        llm.ChatChunk(id="1", delta=llm.ChoiceDelta(content="</thinking>好的。")),
        "<think>private</think>下一个问题？",
        llm.ChatChunk(id="1", usage=usage),
    ]

    async def source(*args):
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(Agent.default, "llm_node", source)

    async def run():
        return [chunk async for chunk in Interviewer.llm_node(object(), None, [], None)]

    output = asyncio.run(run())
    text = "".join(
        chunk if isinstance(chunk, str) else chunk.delta.content or ""
        for chunk in output
        if isinstance(chunk, str) or chunk.delta
    )
    assert text == "好的。下一个问题？"
    assert output[1].delta.tool_calls == [tool]
    assert output[1].delta.extra == {"signature": "keep"}
    assert output[-1].usage == usage
    assert chunks[1].delta.content == "nking>Save first."


@pytest.mark.parametrize("model", ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M3.1"])
def test_minimax_stream_separates_reasoning_from_spoken_content(model):
    pytest.importorskip("livekit.agents")
    import httpx
    from livekit.agents import llm
    from openai import AsyncOpenAI

    from app.services.live.minimax_llm import MiniMaxLLM

    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        deltas = [
            {"role": "assistant", "reasoning_content": "Let me save and then move."},
            {"content": "好的，谢谢你的介绍。"},
            {"content": "接下来请分享项目经历。"},
        ]
        events = [
            {
                "id": "reply-1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            for delta in deltas
        ]
        events.append(
            {
                "id": "reply-1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = AsyncOpenAI(
                api_key="test", base_url="https://example.com/v1", http_client=http
            )
            model_llm = MiniMaxLLM(
                model=model, client=client, extra_body={"reasoning_split": False, "custom": "keep"}
            )
            ctx = llm.ChatContext()
            ctx.add_message(role="user", content="我的自我介绍。")
            async with model_llm.chat(chat_ctx=ctx) as stream:
                return "".join(
                    [
                        chunk.delta.content
                        async for chunk in stream
                        if chunk.delta and chunk.delta.content
                    ]
                )

    assert asyncio.run(run()) == "好的，谢谢你的介绍。接下来请分享项目经历。"
    assert requests[0]["reasoning_split"] is True
    assert requests[0]["custom"] == "keep"
    assert requests[0]["parallel_tool_calls"] is False
    if model == "MiniMax-M3":
        assert requests[0]["thinking"] == {"type": "disabled"}
    else:
        assert "thinking" not in requests[0]
