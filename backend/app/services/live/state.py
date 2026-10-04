"""不依赖 LiveKit 的确定性面试状态操作，便于离线测试和关闭时恢复回答。

ctx 保存权威游标和答案；transcript 保留原始发言。时间戳由调用方提供。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from ...schemas.shared_models import AnswerRecord

if TYPE_CHECKING:
    from ...schemas.shared_models import InterviewContext, PlannedQuestion, ScoreCard, Section

# 难度方向仅为建议，不推进游标或修改状态。
Recommendation = Literal["harder", "easier", "advance", "wrap"]

# 以回答长度作为可复现的节奏信号，仅为启发式，不等同于能力评分。
_THIN_WORDS = 12
_RICH_WORDS = 80
# 计划难度已在最高档时不再建议加难。
_MAX_DIFFICULTY = 5

# 恢复回答须达到最小内容长度，避免问候或零碎发言触发误导性的低分报告。
_MIN_RECOVERED_WORDS = _THIN_WORDS


@dataclass
class InterviewUserdata:
    """单场面试的共享状态；追问标记用于阻止模型在候选人补答前保存或跳题。"""

    ctx: InterviewContext
    session_id: str
    transcript: list[dict] = field(default_factory=list)
    time_limit_reached: bool = False
    closing: bool = False
    followup_pending_question_id: str = ""
    followup_after_user_turn: int = 0
    followup_asked_question_ids: set[str] = field(default_factory=set)


def spoken_answer(ud: InterviewUserdata) -> str:
    """收集当前题的候选人原始发言，包含追问回答。"""
    q = current_question(ud)
    if q is None:
        return ""
    return " ".join(
        t["text"].strip() for t in ud.transcript
        if t.get("role") == "user" and t.get("question_id") == q.id
        and (t.get("text") or "").strip()
    )


def current_answer_saved(ud: InterviewUserdata) -> bool:
    """当前题须同时有真实发言及至少一条非空已存答案，才允许工具推进。"""
    q = current_question(ud)
    return q is not None and bool(spoken_answer(ud)) and any(
        a.question_id == q.id and a.transcript.strip() for a in ud.ctx.answers
    )


def current_question(ud: InterviewUserdata) -> PlannedQuestion | None:
    """返回游标指向的问题，越过计划末尾时返回 None。"""
    questions = ud.ctx.plan.questions
    cursor = ud.ctx.cursor
    if 0 <= cursor < len(questions):
        return questions[cursor]
    return None


def current_section(ud: InterviewUserdata) -> Section | None:
    """返回当前问题的环节，计划结束时返回 None。"""
    q = current_question(ud)
    return q.section if q is not None else None


def advance(ud: InterviewUserdata) -> None:
    """游标前进一题，允许越过计划末尾。"""
    ud.ctx.cursor += 1


def is_complete(ud: InterviewUserdata) -> bool:
    """判断游标是否已越过最后一道计划题。"""
    return ud.ctx.cursor >= len(ud.ctx.plan.questions)


def save_answer(
    ud: InterviewUserdata,
    *,
    transcript: str,
    started_at: str,
    ended_at: str,
) -> AnswerRecord:
    """追加当前题的回答并返回记录；不会去重。

    游标越界时仍追加 question_id 为空的记录，由调用方负责阻止无效保存。
    """
    q = current_question(ud)
    question_id = q.id if q is not None else ""
    record = AnswerRecord(
        question_id=question_id,
        transcript=transcript,
        started_at=started_at,
        ended_at=ended_at,
    )
    ud.ctx.answers.append(record)
    return record


def next_section(ud: InterviewUserdata) -> PlannedQuestion | None:
    """跳过当前环节余题，返回后续首个不同环节的问题；无后续环节时游标置于末尾。"""
    questions = ud.ctx.plan.questions
    starting_section = current_section(ud)

    if starting_section is None:
        ud.ctx.cursor = len(questions)
        return None

    cursor = ud.ctx.cursor
    while cursor < len(questions) and questions[cursor].section == starting_section:
        cursor += 1
    ud.ctx.cursor = cursor
    return questions[cursor] if cursor < len(questions) else None


def add_turn(ud: InterviewUserdata, role: str, text: str) -> None:
    """记录真实发言并标注发言时的题号，供关闭时恢复未保存回答。

    游标越界时题号为空；转录保留原话而非工具提供的摘要。
    """
    q = current_question(ud)
    question_id = q.id if q is not None else ""
    ud.transcript.append({"role": role, "text": text, "question_id": question_id})
    if (
        role == "user"
        and question_id == ud.followup_pending_question_id
        and _user_turn_count(ud, question_id) > ud.followup_after_user_turn
    ):
        ud.followup_pending_question_id = ""
        ud.followup_after_user_turn = 0


def mark_followup_pending(ud: InterviewUserdata) -> bool:
    """要求追问后出现新的候选人发言，避免原回答同时被当作追问答案。

    应在追问流式输出时设置标记，先于同次模型响应中的保存或推进工具。
    """
    q = current_question(ud)
    if q is None or not spoken_answer(ud):
        return False
    if ud.followup_pending_question_id == q.id:
        return True
    ud.followup_asked_question_ids.add(q.id)
    ud.followup_pending_question_id = q.id
    ud.followup_after_user_turn = _user_turn_count(ud, q.id)
    return True


def followup_was_asked(ud: InterviewUserdata) -> bool:
    """判断当前计划题是否已经提出过可选追问。"""
    q = current_question(ud)
    return q is not None and q.id in ud.followup_asked_question_ids


def followup_is_pending(ud: InterviewUserdata) -> bool:
    """判断当前追问是否还在等待新的候选人发言；失效标记会被清除。"""
    qid = ud.followup_pending_question_id
    if not qid:
        return False
    q = current_question(ud)
    if q is None or q.id != qid:
        # 旧状态或恢复流程可能已推进游标，清除失效追问标记以免会话卡住。
        ud.followup_pending_question_id = ""
        ud.followup_after_user_turn = 0
        return False
    if _user_turn_count(ud, qid) > ud.followup_after_user_turn:
        ud.followup_pending_question_id = ""
        ud.followup_after_user_turn = 0
        return False
    return True


def _user_turn_count(ud: InterviewUserdata, question_id: str) -> int:
    return sum(
        1
        for turn in ud.transcript
        if turn.get("role") == "user" and turn.get("question_id") == question_id
        and (turn.get("text") or "").strip()
    )


def reconstruct_answers(ud: InterviewUserdata) -> int:
    """关闭时按 question_id 合并候选人原话，补回尚未保存的有效回答。

    与评分索引一致，以最后一条答案判断是否已保存；空记录不阻止恢复。
    恢复内容须达到最小长度，时间戳留空，返回新增记录数。
    题号取自发言时的游标，游标前进后的重叠发言可能归入下一题。
    """
    last_by_qid: dict[str, AnswerRecord] = {}
    for a in ud.ctx.answers:
        last_by_qid[a.question_id] = a
    saved = {qid for qid, a in last_by_qid.items() if (a.transcript or "").strip()}
    spoken: dict[str, list[str]] = {}
    for turn in ud.transcript:
        qid = turn.get("question_id") or ""
        text = (turn.get("text") or "").strip()
        if turn.get("role") != "user" or not qid or not text or qid in saved:
            continue
        spoken.setdefault(qid, []).append(text)
    added = 0
    for qid, texts in spoken.items():
        joined = " ".join(texts)
        if _word_count(joined) < _MIN_RECOVERED_WORDS:
            continue
        ud.ctx.answers.append(
            AnswerRecord(
                question_id=qid,
                transcript=joined,
                started_at="",
                ended_at="",
            )
        )
        added += 1
    return added


# 不依赖 LiveKit 的自适应难度启发式。


@dataclass(frozen=True)
class DifficultySignal:
    """从计划、游标和已保存回答推导当前环节的难度建议，不修改状态。

    recommendation 为方向，rationale 为可直接提供给实时模型的简短理由。
    """

    recommendation: Recommendation
    section: Section | None
    answered_in_section: int
    section_size: int
    avg_answer_words: float
    current_difficulty: int
    rationale: str


def _answers_by_question_id(ud: InterviewUserdata) -> dict[str, AnswerRecord]:
    """按题号索引已保存回答，重复题号取最后一条。"""
    by_id: dict[str, AnswerRecord] = {}
    for a in ud.ctx.answers:
        by_id[a.question_id] = a
    return by_id


def _word_count(text: str) -> int:
    # 中文和日文可能没有空格，按汉字或假名计数，避免整段回答被误判为一个词。
    return len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff]|[^\s\u3400-\u9fff\u3040-\u30ff]+", text))


def evaluate_difficulty(ud: InterviewUserdata) -> DifficultySignal:
    """依据当前环节已保存答案的平均长度给出建议，不修改面试状态。

    无答案时保持计划；短答案建议降低难度，长答案且未达难度上限时建议加难；
    游标越过计划末尾时建议收尾。长度是启发式信号，不等同于能力评分。
    """
    section = current_section(ud)
    if section is None:
        return DifficultySignal(
            recommendation="wrap",
            section=section,
            answered_in_section=0,
            section_size=0,
            avg_answer_words=0.0,
            current_difficulty=0,
            rationale="Past the planned questions — wrap up.",
        )

    questions = ud.ctx.plan.questions
    section_qs = [q for q in questions if q.section == section]
    section_size = len(section_qs)
    by_id = _answers_by_question_id(ud)
    answered = [
        by_id[q.id] for q in section_qs if q.id in by_id
    ]
    answered_in_section = len(answered)

    current = current_question(ud)
    current_difficulty = current.difficulty if current is not None else 0

    if answered_in_section == 0:
        # 当前环节尚无有效证据，保持原计划。
        return DifficultySignal(
            recommendation="advance",
            section=section,
            answered_in_section=0,
            section_size=section_size,
            avg_answer_words=0.0,
            current_difficulty=current_difficulty,
            rationale=(
                f"No answers yet in the {section} section — proceed as planned."
            ),
        )

    total_words = sum(_word_count(a.transcript) for a in answered)
    avg_words = total_words / answered_in_section

    if avg_words < _THIN_WORDS:
        rec: Recommendation = "easier"
        rationale = (
            f"Answers in the {section} section are thin "
            f"(~{avg_words:.0f} words) — ease off and ask something more concrete."
        )
    elif avg_words > _RICH_WORDS and current_difficulty < _MAX_DIFFICULTY:
        rec = "harder"
        rationale = (
            f"Answers in the {section} section are strong "
            f"(~{avg_words:.0f} words) — push to a harder, deeper question."
        )
    else:
        rec = "advance"
        rationale = (
            f"The {section} section is well covered "
            f"({answered_in_section}/{section_size} answered) — move on."
        )

    return DifficultySignal(
        recommendation=rec,
        section=section,
        answered_in_section=answered_in_section,
        section_size=section_size,
        avg_answer_words=avg_words,
        current_difficulty=current_difficulty,
        rationale=rationale,
    )


def difficulty_hint(ud: InterviewUserdata) -> str:
    """生成 recommendation: rationale 格式的简短模型提示。"""
    sig = evaluate_difficulty(ud)
    return f"{sig.recommendation}: {sig.rationale}"


def compact_summary(ud: InterviewUserdata) -> str:
    """拼接候选人摘要及目标岗位，供实时指令使用，不加入完整简历、职位或公司资料。"""
    cand = ud.ctx.candidate
    job = ud.ctx.job
    role = f"{job.title} ({job.seniority}) at {job.company_name}"
    return (
        f"Candidate: {cand.name}, {cand.headline}. "
        f"Interviewing for: {role}. "
        f"{cand.summary_120w}"
    )


def weak_areas_summary(scorecard: ScoreCard | None) -> str:
    """按评分卡弱项原顺序生成语音教练摘要；未评分或无弱项时返回鼓励性引导。"""
    if scorecard is None:
        return (
            "No scorecard yet for this session. Ask the candidate which area they "
            "want to work on and coach from there."
        )
    weak = list(scorecard.weak_competencies)
    if not weak:
        return (
            "No specific weak areas from the last interview. Reinforce strengths "
            "and run a quick refresher on the candidate's chosen topic."
        )
    return "Focus areas from the last interview (weakest first): " + ", ".join(weak) + "."
