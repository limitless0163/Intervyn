"""适配 MiniMax 的会话消息要求，并分离推理、串行执行状态工具。

仅在发出的请求副本中补开场消息，不把虚构候选人发言写入转录或评分上下文。
"""

from livekit.agents import llm
from livekit.plugins import openai


class MiniMaxLLM(openai.LLM):
    """隔离推理、串行化状态工具，并为纯系统消息的开场请求补充会话消息。"""
    def __init__(self, **kwargs):
        # 分离推理字段，避免 delta.content 中的私有推理被播报或显示成字幕。
        extra_body = dict(kwargs.pop("extra_body", None) or {})
        extra_body["reasoning_split"] = True
        if kwargs.get("model", "").lower() == "minimax-m3":
            extra_body["thinking"] = {"type": "disabled"}
        super().__init__(extra_body=extra_body, **kwargs)

    def chat(self, *, chat_ctx: llm.ChatContext, **kwargs):
        # 保存必须先于推进完成，禁用并行工具调用以免状态竞争。
        kwargs["parallel_tool_calls"] = False
        if not any(
            isinstance(item, llm.ChatMessage) and item.role in {"user", "assistant"}
            for item in chat_ctx.items
        ):
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(
                role="user", content="Begin the interview following the instructions."
            )
        return super().chat(chat_ctx=chat_ctx, **kwargs)
