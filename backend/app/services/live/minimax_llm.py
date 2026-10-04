"""MiniMax's OpenAI-compatible API requires a conversational message.

LiveKit's proactive generate_reply(instructions=...) starts with only system
messages. Seed only the outgoing request, so the opener works without recording
an invented candidate answer in the transcript or the scoring context.
"""

from livekit.agents import llm
from livekit.plugins import openai


class MiniMaxLLM(openai.LLM):
    def __init__(self, **kwargs):
        # Otherwise MiniMax sends its private reasoning in delta.content,
        # where LiveKit treats it as speech and publishes it as captions.
        extra_body = dict(kwargs.pop("extra_body", None) or {})
        extra_body["reasoning_split"] = True
        if kwargs.get("model", "").lower() == "minimax-m3":
            extra_body["thinking"] = {"type": "disabled"}
        super().__init__(extra_body=extra_body, **kwargs)

    def chat(self, *, chat_ctx: llm.ChatContext, **kwargs):
        # save_answer must finish before get_next_question reads its result.
        # Do not allow the provider to race state-changing tools in one batch.
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
