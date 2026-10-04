"""The base live interviewer :class:`Agent` and its turn-path tools.

REQUIRES the optional ``livekit-agents`` extra (``uv sync --extra livekit``);
imports ``livekit.agents`` at load time, so it is imported lazily by the worker
and NOT by ``live/__init__.py`` (offline ``import ...live.state`` stays clean).

Design rules (project golden rule #2: keep the live loop lean):
- The prompt injects ONLY the compact candidate summary + the current question +
  recent turns — never the whole CV / JD / company intel.
- ``@function_tool`` methods mutate the local :class:`InterviewUserdata` ONLY.
  No network / DB on the turn path; persistence + scoring happen on shutdown
  (see ``worker.py``).
- Handoffs return a fresh persona agent (``CodingRoundAgent`` / ``BehavioralAgent``)
  to switch styles natively while keeping the same session userdata. Personas
  subclass ``Interviewer`` (tools are per-agent in livekit-agents 1.x) and get
  the running ``chat_ctx`` so the conversation history survives the handoff.
- The flat ``ud.transcript`` log is fed by the worker's ``conversation_item_added``
  listener (real STT/agent turns) — tools no longer write to it, so answers are
  captured even when the model forgets to call ``save_answer``.
"""

from __future__ import annotations

from livekit.agents import Agent, RunContext, StopResponse, function_tool, llm

from ...core.logging import get_logger
from . import state
from .reasoning import ReasoningFilter
from .state import InterviewUserdata

log = get_logger(__name__)


def _localized(text: dict[str, str], primary: str) -> str:
    """Resolve a ``LocalizedText`` to the primary language, falling back to en."""
    return text.get(primary) or text.get("en") or next(iter(text.values()), "")


def _wrap_signal() -> str:
    return (
        "INTERVIEW_COMPLETE: thank the candidate warmly in one or two sentences, "
        "tell them their feedback report will be ready shortly, and then call "
        "end_interview to close the session."
    )


def _wait_if_candidate_speaking(context: RunContext[InterviewUserdata]) -> None:
    """A resumed answer must not race a pending save/advance/close tool call."""
    if context.session.user_state == "speaking":
        log.info("interview: candidate resumed speaking; deferring progression")
        raise StopResponse()


def _wait_if_followup_pending(context: RunContext[InterviewUserdata]) -> None:
    """Do not treat the answer before a follow-up as its answer too."""
    if state.followup_is_pending(context.userdata):
        log.info(
            "interview: follow-up unanswered; deferring progression cursor=%d",
            context.userdata.ctx.cursor,
        )
        raise StopResponse()


def build_instructions(ud: InterviewUserdata) -> str:
    """Lean per-question system prompt: compact summary + current question."""
    primary = ud.ctx.plan.language_mode.primary
    summary = state.compact_summary(ud)
    q = state.current_question(ud)
    question_line = (
        _localized(q.text, primary) if q is not None else "(no further questions)"
    )
    return (
        "You are a senior, friendly technical interviewer running a real-time "
        "voice mock interview. Speak naturally and concisely.\n\n"
        "Use a calm conversational tone, plain spoken sentences and normal punctuation. "
        "Avoid markdown, bullet lists, dramatic pauses and lengthy repeated summaries.\n\n"
        "Output only words addressed to the candidate in the primary language. "
        "Keep reasoning, answer assessments, tool plans and internal notes private; "
        "never narrate saving answers or selecting the next question.\n\n"
        f"{summary}\n\n"
        f"Primary language: {primary}.\n"
        f"Current question to ask: {question_line}\n\n"
        "Ask one question and wait for the candidate's full answer. You may ask at "
        "most one light follow-up. A follow-up is a separate question: after asking "
        "it, stop immediately and wait for a new candidate answer. The answer to the "
        "original question does not count as an answer to the follow-up. Do not call "
        "save_answer, get_next_question, next_section, or end_interview until that "
        "new answer arrives. When there is no unanswered follow-up, call save_answer "
        "with the candidate's answer, then call get_next_question to proceed. Use "
        "the question returned by get_next_question for the next prompt; do not ask "
        "a later planned question before advancing to it. Call next_section to move "
        "to a different round, and request_clarification only if "
        "the candidate seems confused. Never read the rubric aloud. "
        "After asking a question, STOP and wait for a new candidate answer. "
        "The wrap section contains a real final question: wait for its answer too. "
        "Never invent answers or call progression tools before the candidate responds. "
        "A brief pause or an unfinished thought is not a completed answer. "
        "If the candidate says they are thinking or still have more to add, wait. "
        "If your speech was interrupted, complete or rephrase the unfinished question "
        "before proceeding."
    )


class Interviewer(Agent):
    """The primary interviewer persona; owns the shared interview tools."""

    def __init__(
        self,
        userdata: InterviewUserdata,
        *,
        chat_ctx=None,
        extra_instructions: str = "",
    ) -> None:
        self._extra_instructions = extra_instructions
        instructions = build_instructions(userdata)
        if extra_instructions:
            instructions = f"{instructions}\n\n{extra_instructions}"
        kwargs = {}
        if chat_ctx is not None:
            # Only forward when given: Agent distinguishes NOT_GIVEN from None.
            kwargs["chat_ctx"] = chat_ctx
        super().__init__(instructions=instructions, **kwargs)

    async def llm_node(self, chat_ctx, tools, model_settings):
        # Filter before LiveKit fans text out to TTS, captions and chat history.
        # Each generation (including after a tool call) gets isolated state. Stop
        # spoken output at its first question so one generation cannot ask a
        # follow-up and then continue into the next planned question.
        reasoning = ReasoningFilter()
        question_finished = False
        # Follow-up gating needs the session userdata; if it is unavailable
        # (for example in unit tests that drive ``llm_node`` directly with a
        # stubbed self), fall through to the plain question-truncation behavior.
        ud = getattr(getattr(self, "session", None), "userdata", None)
        if ud is not None:
            active_question = state.current_question(ud)
            answered_followup_question_id = (
                active_question.id
                if active_question is not None and state.followup_was_asked(ud)
                else ""
            )
        else:
            active_question = None
            answered_followup_question_id = ""

        def public_text(text: str) -> str:
            nonlocal question_finished
            if not text or question_finished:
                return ""
            current = state.current_question(ud) if ud is not None else None
            if (
                answered_followup_question_id
                and current is not None
                and current.id == answered_followup_question_id
            ):
                # The candidate has answered the follow-up, so the model must
                # save and advance before saying anything about the next item.
                return ""
            boundary = next(
                (index for index, char in enumerate(text) if char in {"?", "？"}),
                -1,
            )
            if boundary < 0:
                return text

            # If this question follows a candidate answer on the active planned
            # question, it is a follow-up. Record the wait before tool calls from
            # this same response can save or advance the interview.
            if ud is not None and state.spoken_answer(ud) and state.mark_followup_pending(ud):
                q = state.current_question(ud)
                log.info(
                    "interview: follow-up asked; waiting for candidate cursor=%d question=%s",
                    ud.ctx.cursor,
                    q.id if q is not None else "",
                )
            question_finished = True
            return text[: boundary + 1]

        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, str):
                text = public_text(reasoning.feed(chunk))
                if text:
                    yield text
            elif isinstance(chunk, llm.ChatChunk) and chunk.delta and chunk.delta.content:
                text = public_text(reasoning.feed(chunk.delta.content))
                delta = chunk.delta.model_copy(
                    update={"content": text or None}
                )
                # Preserve tool calls, usage and provider metadata even when
                # this chunk's entire text was private reasoning.
                yield chunk.model_copy(update={"delta": delta})
            else:
                yield chunk
        reasoning.finish()

    async def on_enter(self) -> None:
        """Open the interview proactively: greet the candidate and ask Q1.

        LiveKit calls this when the agent becomes the active speaker. Without it
        the agent stays silent until the candidate speaks first (the avatar sits
        on its idle loop). We drive the first turn with ``generate_reply``
        (synchronous in livekit-agents 1.x — returns a SpeechHandle) using the
        lean context already in the system prompt; subsequent turns flow through
        the tools. Round personas override this opener with a round transition
        (see ``handoffs.py``), so the greeting fires only for the base interviewer.
        """
        ud = self.session.userdata
        primary = ud.ctx.plan.language_mode.primary
        q = state.current_question(ud)
        question_line = (
            _localized(q.text, primary) if q is not None else "(no further questions)"
        )
        first_name = (ud.ctx.candidate.name or "there").split()[0]
        if q is None:
            return
        # The opener is precomputed; do not make a speculative LLM request that
        # can rewrite/cut Q1 or call progression tools before the first answer.
        if primary == "zh":
            greeting = (
                f"{first_name}，你好！今天由我来进行{ud.ctx.job.company_name}的"
                f"{ud.ctx.job.title}岗位模拟面试。"
            )
        else:
            greeting = None
        if greeting:
            self.session.say(f"{greeting} {question_line}")
        else:
            self.session.generate_reply(
                instructions=(
                    f"In {primary}, greet {first_name} briefly, then ask exactly this "
                    f"question and STOP to wait for their answer: {question_line}"
                ),
                tool_choice="none",
            )

    @function_tool
    async def save_answer(
        self,
        context: RunContext[InterviewUserdata],
        answer: str,
        started_at: str = "",
        ended_at: str = "",
    ) -> str:
        """Record the candidate's answer to the current question.

        Call this once the candidate has finished answering the question and any
        follow-up you asked, BEFORE get_next_question. ``answer`` is the
        candidate's spoken answer text.
        """
        _wait_if_candidate_speaking(context)
        _wait_if_followup_pending(context)
        ud = context.userdata
        spoken = state.spoken_answer(ud)
        if not spoken:
            log.warning("interview: save rejected without user speech cursor=%d", ud.ctx.cursor)
            return "No candidate answer received for this question. Ask it and WAIT."
        record = state.save_answer(
            ud, transcript=spoken, started_at=started_at, ended_at=ended_at
        )
        log.info("interview: saved question=%s chars=%d", record.question_id, len(spoken))
        return f"Saved answer for question {record.question_id}."

    async def _refresh_instructions(self, ud: InterviewUserdata) -> None:
        """Re-sync the system prompt with the advanced cursor (best-effort).

        Without this the prompt keeps saying "Current question to ask: <Q1>" for
        the whole interview, contradicting the tool-returned questions. Never
        allowed to break a turn.
        """
        try:
            instructions = build_instructions(ud)
            if self._extra_instructions:
                instructions += f"\n\n{self._extra_instructions}"
            await self.update_instructions(instructions)
        except Exception:
            log.exception("interview: instruction refresh failed cursor=%d", ud.ctx.cursor)

    @function_tool
    async def get_next_question(self, context: RunContext[InterviewUserdata]) -> str:
        """Advance after the answer and any follow-up reply, then return the next question."""
        _wait_if_candidate_speaking(context)
        _wait_if_followup_pending(context)
        ud = context.userdata
        if state.is_complete(ud):
            return _wrap_signal()
        if not state.current_answer_saved(ud):
            log.warning("interview: advance rejected for unanswered question cursor=%d", ud.ctx.cursor)
            return "Save the actual answer to the current question first. If unanswered, WAIT."
        if ud.time_limit_reached:
            ud.ctx.cursor = len(ud.ctx.plan.questions)
            return _wrap_signal()
        state.advance(ud)
        log.info("interview: advanced cursor=%d", ud.ctx.cursor)
        if state.is_complete(ud):
            return _wrap_signal()
        q = state.current_question(ud)
        assert q is not None  # not complete -> a current question exists
        primary = ud.ctx.plan.language_mode.primary
        text = _localized(q.text, primary)
        await self._refresh_instructions(ud)
        return f"Next question ({q.section}): {text}\nAsk this question, then STOP and WAIT for the candidate."

    @function_tool
    async def next_section(self, context: RunContext[InterviewUserdata]) -> str:
        """Skip to the first question of the next section (or wrap if none)."""
        _wait_if_candidate_speaking(context)
        _wait_if_followup_pending(context)
        ud = context.userdata
        if state.is_complete(ud):
            return _wrap_signal()
        if not state.current_answer_saved(ud):
            return "The current question is unanswered or unsaved. Finish it before switching sections."
        if ud.time_limit_reached:
            ud.ctx.cursor = len(ud.ctx.plan.questions)
            return _wrap_signal()
        q = state.next_section(ud)
        if q is None:
            return _wrap_signal()
        primary = ud.ctx.plan.language_mode.primary
        text = _localized(q.text, primary)
        await self._refresh_instructions(ud)
        return f"Moving to {q.section}: {text}\nAsk this question, then STOP and WAIT for the candidate."

    @function_tool
    async def get_difficulty_hint(
        self, context: RunContext[InterviewUserdata]
    ) -> str:
        """Advisory hint on whether to go harder/easier, advance, or wrap.

        OPTIONAL and non-binding: consult it only if you're unsure how to pace the
        current section. It is computed locally from answers already given (no
        network, no blocking) and never changes the question cursor.
        """
        return state.difficulty_hint(context.userdata)

    @function_tool
    async def request_clarification(
        self, context: RunContext[InterviewUserdata], reason: str = ""
    ) -> str:
        """Note that the candidate needs the current question rephrased."""
        ud = context.userdata
        q = state.current_question(ud)
        if q is None:
            return "No active question to clarify."
        primary = ud.ctx.plan.language_mode.primary
        return (
            "Rephrase the current question more simply, keeping the same intent: "
            f"{_localized(q.text, primary)}"
        )

    @function_tool
    async def end_interview(self, context: RunContext[InterviewUserdata]) -> str:
        """End the interview session AFTER saying goodbye.

        Call this once you have thanked the candidate and said the report is on
        its way. It drains the current speech, then closes the session — which
        triggers the worker's persist + score shutdown path. Without it a
        finished interview idles until the hard duration guard trips.
        """
        _wait_if_candidate_speaking(context)
        _wait_if_followup_pending(context)
        if not state.is_complete(context.userdata):
            return "The interview still has an active question. Wait for its answer before ending."
        context.userdata.closing = True
        try:
            self.session.shutdown(drain=True)
        except Exception:  # noqa: BLE001, S110 - closing must never raise into the turn
            pass
        return "Interview ended. Say nothing further."

    @function_tool
    async def start_coding_round(self, context: RunContext[InterviewUserdata]) -> Agent:
        """Hand off to the coding-round persona (native LiveKit agent handoff)."""
        from .handoffs import CodingRoundAgent

        return CodingRoundAgent(context.userdata, chat_ctx=self.chat_ctx)

    @function_tool
    async def start_behavioral_round(
        self, context: RunContext[InterviewUserdata]
    ) -> Agent:
        """Hand off to the behavioral-round persona (native LiveKit agent handoff)."""
        from .handoffs import BehavioralAgent

        return BehavioralAgent(context.userdata, chat_ctx=self.chat_ctx)
