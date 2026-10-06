"""实时面试角色及本地状态工具，需安装 livekit 扩展，由工作进程按需导入。

提示词只包含摘要和当前题；转录由工作进程监听真实发言，持久化在后台检查点和关闭回调执行。
角色交接继承工具并保留聊天历史。工具文档字符串同时作为模型可见的调用说明。
"""

from __future__ import annotations

from livekit.agents import Agent, RunContext, StopResponse, function_tool, llm

from ...core.logging import get_logger
from . import state
from .reasoning import ReasoningFilter
from .state import InterviewUserdata

log = get_logger(__name__)


def _localized(text: dict[str, str], primary: str) -> str:
    """优先使用主语言，其次英语，最后回退到任意已有译文。"""
    return text.get(primary) or text.get("en") or next(iter(text.values()), "")


def _wrap_signal() -> str:
    return (
        "INTERVIEW_COMPLETE: thank the candidate warmly in one or two sentences, "
        "tell them their feedback report will be ready shortly, and then call "
        "end_interview to close the session."
    )


def _wait_if_candidate_speaking(context: RunContext[InterviewUserdata]) -> None:
    """候选人恢复讲话时暂停保存、推进和关闭，避免未完成回答与工具调用竞争。"""
    if context.session.user_state == "speaking":
        log.info("interview: candidate resumed speaking; deferring progression")
        raise StopResponse()


def _wait_if_followup_pending(context: RunContext[InterviewUserdata]) -> None:
    """追问尚无新回答时暂停工具调用，避免把原回答同时算作追问答案。"""
    if state.followup_is_pending(context.userdata):
        log.info(
            "interview: follow-up unanswered; deferring progression cursor=%d",
            context.userdata.ctx.cursor,
        )
        raise StopResponse()


def build_instructions(ud: InterviewUserdata) -> str:
    """构造每题的紧凑系统指令，注入候选人及公司研究摘要与当前问题。"""
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
    """基础面试角色，持有各环节共用的面试工具。"""

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
            # 只在明确提供历史时传入，避免 None 与 SDK 的未提供哨兵产生不同含义。
            kwargs["chat_ctx"] = chat_ctx
        super().__init__(instructions=instructions, **kwargs)

    async def llm_node(self, chat_ctx, tools, model_settings):
        # 在文本送往语音、字幕及历史前过滤推理；每次生成使用独立状态。
        # 首个问号后停止正文，防止一次响应同时追问并提出下一题。
        reasoning = ReasoningFilter()
        question_finished = False
        # 没有会话状态时只截断问题，兼容直接调用流式节点的测试桩。
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
                # 追问已有回答时，必须先保存并推进才能发出下一题，避免游标与发问错位。
                return ""
            boundary = next(
                (index for index, char in enumerate(text) if char in {"?", "？"}),
                -1,
            )
            if boundary < 0:
                return text

            # 原题已有候选人发言后的新问句视为追问，先设等待标记阻止同一响应内提前推进。
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
                # 正文即使被全部过滤，仍保留工具调用、用量及提供方元数据。
                yield chunk.model_copy(update={"delta": delta})
            else:
                yield chunk
        reasoning.finish()

    async def on_enter(self) -> None:
        """主动问候并提出首题；中文使用预生成开场，其他语言禁用工具生成开场。

        环节角色会覆盖此方法，只做环节过渡，不重复问候。
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
        # 中文开场直接播报预生成文本，其他语言生成开场时禁用工具，避免首答前推进游标。
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
        """候选人完成当前题及追问后保存回答，必须先于 get_next_question 调用。

        answer 保留为工具参数；实际保存按当前题采集的原始发言，避免模型改写回答。
        started_at 和 ended_at 为可选时间戳，未提供时留空。
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
        """游标推进后同步系统指令，避免旧题与工具返回的新题冲突；更新失败不打断轮次。"""
        try:
            instructions = build_instructions(ud)
            if self._extra_instructions:
                instructions += f"\n\n{self._extra_instructions}"
            await self.update_instructions(instructions)
        except Exception:
            log.exception("interview: instruction refresh failed cursor=%d", ud.ctx.cursor)

    @function_tool
    async def get_next_question(self, context: RunContext[InterviewUserdata]) -> str:
        """当前题及追问已回答并保存后推进，返回下一题；无后续题或触限时返回收尾指令。"""
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
        assert q is not None
        primary = ud.ctx.plan.language_mode.primary
        text = _localized(q.text, primary)
        await self._refresh_instructions(ud)
        return f"Next question ({q.section}): {text}\nAsk this question, then STOP and WAIT for the candidate."

    @function_tool
    async def next_section(self, context: RunContext[InterviewUserdata]) -> str:
        """当前题完成并保存后跳过本环节余题，返回下一环节首题；无后续环节则收尾。"""
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
        """仅在需要节奏建议时读取本地难度提示，可建议加难、降难、推进或收尾。

        此提示非强制，不联网、不修改游标，仅依据现有回答计算。
        """
        return state.difficulty_hint(context.userdata)

    @function_tool
    async def request_clarification(
        self, context: RunContext[InterviewUserdata], reason: str = ""
    ) -> str:
        """返回重述当前题的指令，保留问题原意；不修改游标或存储状态。"""
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
        """计划已结束、候选人和追问都已回答后，先道谢并告知报告即将生成，再调用此工具。

        等当前语音播完后关闭会话，触发工作进程的持久化及评分；不得提前结束未答题。
        """
        _wait_if_candidate_speaking(context)
        _wait_if_followup_pending(context)
        if not state.is_complete(context.userdata):
            return "The interview still has an active question. Wait for its answer before ending."
        context.userdata.closing = True
        try:
            self.session.shutdown(drain=True)
        except Exception:  # noqa: BLE001, S110 - 关闭失败不能打断当前轮次
            pass
        return "Interview ended. Say nothing further."

    @function_tool
    async def start_coding_round(self, context: RunContext[InterviewUserdata]) -> Agent:
        """交接到编码面试角色，保留共享状态与聊天历史。"""
        from .handoffs import CodingRoundAgent

        return CodingRoundAgent(context.userdata, chat_ctx=self.chat_ctx)

    @function_tool
    async def start_behavioral_round(
        self, context: RunContext[InterviewUserdata]
    ) -> Agent:
        """交接到行为面试角色，保留共享状态与聊天历史。"""
        from .handoffs import BehavioralAgent

        return BehavioralAgent(context.userdata, chat_ctx=self.chat_ctx)
