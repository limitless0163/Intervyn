"""通过 LiveKit 角色交接切换编码和行为面试，需安装 livekit 扩展。

各角色继承 Interviewer 以保留工具，并传入 chat_ctx 保留历史；进入后主动开启当前环节。
"""

from __future__ import annotations

from . import state
from .interviewer import Interviewer, _localized

_CODING_INSTRUCTIONS = (
    "You are now running the CODING round. Pose one focused, hands-on problem "
    "tied to the candidate's stack. Ask them to think aloud; if you ask a hint or "
    "follow-up question, stop and wait for the candidate to answer it. Do not "
    "lecture. When the problem is resolved or time is tight and there is no "
    "unanswered follow-up, call save_answer then get_next_question."
)

_BEHAVIORAL_INSTRUCTIONS = (
    "You are now running the BEHAVIORAL round. Ask one STAR-style question at a "
    "time about real past experience. Listen, then ask at most one probing "
    "follow-up for specifics (the 'I' not the 'we'). Stop after asking it and "
    "wait for a new candidate answer before saving or advancing. Warm, concise, "
    "never leading."
)


class _RoundPersona(Interviewer):
    """共享完整面试工具，并为新环节提供主动开场。"""

    _round_label = "next"

    def __init__(self, userdata, chat_ctx=None) -> None:
        super().__init__(
            userdata,
            chat_ctx=chat_ctx,
            extra_instructions=self._round_instructions(),
        )

    def _round_instructions(self) -> str:
        raise NotImplementedError

    async def on_enter(self) -> None:
        """主动过渡到新环节并询问当前题，避免面试中途重复自我介绍。"""
        ud = self.session.userdata
        primary = ud.ctx.plan.language_mode.primary
        q = state.current_question(ud)
        question_line = (
            _localized(q.text, primary) if q is not None else "(no further questions)"
        )
        self.session.generate_reply(
            instructions=(
                f"Transition smoothly into the {self._round_label} round, speaking "
                f"in {primary}. In one short sentence say you're moving to this "
                f"round, then ask this question and stop: {question_line}. Do not "
                "re-introduce yourself or call any tools yet."
            ),
            tool_choice="none",
        )


class CodingRoundAgent(_RoundPersona):
    """编码面试角色。"""

    _round_label = "coding"

    def _round_instructions(self) -> str:
        return _CODING_INSTRUCTIONS


class BehavioralAgent(_RoundPersona):
    """行为面试角色。"""

    _round_label = "behavioral"

    def _round_instructions(self) -> str:
        return _BEHAVIORAL_INSTRUCTIONS
