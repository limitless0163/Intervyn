"""离线验证面试状态机及转录恢复；每项测试独立创建状态，避免游标修改相互影响。

默认模拟计划仅有一道 intro 题，跨环节测试额外追加 behavioral 题。
"""

from __future__ import annotations

import asyncio

from app.dependencies.container import build_deps
from app.schemas.shared_models import (
    AnswerRecord,
    InterviewContext,
    LanguageMode,
    PrepRequest,
)
from app.services.live import state
from app.services.live.state import InterviewUserdata
from app.services.prep.pipeline import run_prep


def _build_context() -> InterviewContext:
    """运行模拟准备流程并读取有效面试上下文。"""
    deps = build_deps()
    req = PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary="en", mixed=False),
    )
    session_id = asyncio.run(run_prep(req, deps))
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    return ctx


def _userdata() -> InterviewUserdata:
    ctx = _build_context()
    return InterviewUserdata(ctx=ctx, session_id=ctx.session_id)


def _userdata_two_sections() -> InterviewUserdata:
    """构造含两个不同环节题目的独立状态。"""
    ctx = _build_context()
    first = ctx.plan.questions[0]
    second = first.model_copy(update={"id": "q_behavioral", "section": "behavioral"})
    ctx.plan.questions.append(second)
    return InterviewUserdata(ctx=ctx, session_id=ctx.session_id)


def test_current_question_returns_first_question() -> None:
    ud = _userdata()
    q = state.current_question(ud)
    assert q is not None
    assert q is ud.ctx.plan.questions[0]
    assert ud.ctx.cursor == 0


def test_advance_moves_cursor() -> None:
    ud = _userdata()
    assert ud.ctx.cursor == 0
    state.advance(ud)
    assert ud.ctx.cursor == 1


def test_save_answer_appends_record_with_matching_question_id() -> None:
    ud = _userdata()
    current = state.current_question(ud)
    assert current is not None

    record = state.save_answer(
        ud,
        transcript="I led the migration to a sharded payments ledger.",
        started_at="2026-06-08T09:00:00Z",
        ended_at="2026-06-08T09:01:30Z",
    )

    assert isinstance(record, AnswerRecord)
    assert record.question_id == current.id
    assert ud.ctx.answers[-1] is record
    assert len(ud.ctx.answers) == 1
    assert record.transcript.startswith("I led the migration")


def test_advance_until_complete_then_no_current_question() -> None:
    ud = _userdata()
    assert not state.is_complete(ud)

    # 推进次数限定为计划题数，避免测试本身无限循环。
    steps = 0
    max_steps = len(ud.ctx.plan.questions) + 5
    while not state.is_complete(ud) and steps < max_steps:
        assert state.current_question(ud) is not None
        state.advance(ud)
        steps += 1

    assert state.is_complete(ud)
    assert state.current_question(ud) is None
    assert state.current_section(ud) is None
    assert ud.ctx.cursor == len(ud.ctx.plan.questions)


def test_next_section_jumps_to_a_different_section() -> None:
    ud = _userdata_two_sections()
    starting = state.current_section(ud)
    assert starting is not None

    nxt = state.next_section(ud)
    assert nxt is not None
    assert nxt.section != starting
    assert state.current_question(ud) is nxt
    assert state.current_section(ud) == nxt.section


def test_next_section_at_end_returns_none() -> None:
    ud = _userdata()
    ud.ctx.cursor = len(ud.ctx.plan.questions)
    assert state.next_section(ud) is None
    assert state.is_complete(ud)


def test_add_turn_and_compact_summary() -> None:
    ud = _userdata()
    q1 = state.current_question(ud)
    assert q1 is not None
    state.add_turn(ud, "assistant", "Tell me about a hard bug you fixed.")
    state.add_turn(ud, "user", "I traced a race condition in our ledger writer.")
    assert ud.transcript == [
        {
            "role": "assistant",
            "text": "Tell me about a hard bug you fixed.",
            "question_id": q1.id,
        },
        {
            "role": "user",
            "text": "I traced a race condition in our ledger writer.",
            "question_id": q1.id,
        },
    ]

    summary = state.compact_summary(ud)
    assert ud.ctx.candidate.name in summary
    assert ud.ctx.job.title in summary
    assert ud.ctx.candidate.summary_120w in summary


def test_add_turn_past_end_has_empty_question_id() -> None:
    ud = _userdata()
    ud.ctx.cursor = len(ud.ctx.plan.questions)
    state.add_turn(ud, "user", "Thanks, goodbye!")
    assert ud.transcript[-1]["question_id"] == ""


def test_reconstruct_answers_recovers_unsaved_user_turns() -> None:
    """候选人断开前未调用保存工具时，真实发言仍须可恢复。"""
    ud = _userdata_two_sections()
    q1 = state.current_question(ud)
    assert q1 is not None
    state.add_turn(ud, "assistant", "Tell me about a hard bug you fixed.")
    state.add_turn(ud, "user", "I traced a race condition in our ledger writer")
    state.add_turn(ud, "user", "by bisecting the commit history and adding a regression test.")
    assert ud.ctx.answers == []

    added = state.reconstruct_answers(ud)

    assert added == 1
    record = ud.ctx.answers[-1]
    assert record.question_id == q1.id
    assert record.transcript == (
        "I traced a race condition in our ledger writer "
        "by bisecting the commit history and adding a regression test."
    )


def test_reconstruct_answers_skips_saved_questions_and_is_idempotent() -> None:
    ud = _userdata_two_sections()
    state.add_turn(
        ud, "user", "raw stt text for question one with enough words to clear the substance gate"
    )
    state.save_answer(
        ud,
        transcript="The model's curated answer for question one.",
        started_at="",
        ended_at="",
    )
    state.advance(ud)
    state.add_turn(
        ud, "user", "an answer the model never saved about leading the on-call rotation overhaul"
    )

    added = state.reconstruct_answers(ud)

    # 仅恢复未保存的第二题，保留第一题已有答案。
    assert added == 1
    assert len(ud.ctx.answers) == 2
    assert ud.ctx.answers[0].transcript.startswith("The model's curated")
    assert ud.ctx.answers[1].question_id == "q_behavioral"
    assert ud.ctx.answers[1].transcript == (
        "an answer the model never saved about leading the on-call rotation overhaul"
    )

    # 重复恢复须幂等。
    assert state.reconstruct_answers(ud) == 0
    assert len(ud.ctx.answers) == 2


def test_reconstruct_answers_ignores_blank_and_assistant_turns() -> None:
    ud = _userdata()
    state.add_turn(ud, "assistant", "Tell me about a hard bug you fixed.")
    state.add_turn(ud, "user", "   ")
    assert state.reconstruct_answers(ud) == 0
    assert ud.ctx.answers == []


# 转录恢复的边界回归。


def test_reconstruct_answers_turns_follow_cursor_across_advances() -> None:
    """按发言时的活动题号分组恢复，游标推进前后的回答不能混入同一题。"""
    ud = _userdata_two_sections()
    q1 = state.current_question(ud)
    assert q1 is not None
    state.add_turn(ud, "user", "first part of answer one about sharding the ledger")
    state.add_turn(ud, "user", "second part of answer one covering the rollout and metrics")

    state.advance(ud)
    q2 = state.current_question(ud)
    assert q2 is not None
    assert q2.id != q1.id
    state.add_turn(
        ud, "user", "the whole of answer two describing how I mentored two junior engineers"
    )

    added = state.reconstruct_answers(ud)

    assert added == 2
    by_id = {a.question_id: a for a in ud.ctx.answers}
    assert set(by_id) == {q1.id, q2.id}
    # 每题只合并自己的转写片段，禁止跨题污染。
    assert by_id[q1.id].transcript == (
        "first part of answer one about sharding the ledger "
        "second part of answer one covering the rollout and metrics"
    )
    assert by_id[q2.id].transcript == (
        "the whole of answer two describing how I mentored two junior engineers"
    )


def test_reconstruct_answers_joins_multi_fragment_answer_in_spoken_order() -> None:
    """同题多个转写片段按发言顺序用空格拼接。"""
    ud = _userdata()
    q1 = state.current_question(ud)
    assert q1 is not None
    # 模拟流式最终转写中可能出现的首尾空白。
    state.add_turn(ud, "user", "  I shipped the ledger")
    state.add_turn(ud, "user", "then I profiled it  ")
    state.add_turn(ud, "user", "and fixed the hot path")

    assert state.reconstruct_answers(ud) == 1
    record = ud.ctx.answers[-1]
    assert record.question_id == q1.id
    assert record.transcript == "I shipped the ledger then I profiled it and fixed the hot path"


def test_reconstruct_answers_preserves_existing_answer_order_for_last_wins() -> None:
    """恢复记录追加在已存记录后；已有有效答案的题目不得再恢复重复记录。"""
    ud = _userdata_two_sections()
    q1 = state.current_question(ud)
    assert q1 is not None
    # 同题同时有足量原话和已保存答案，用于验证已有答案去重规则。
    state.add_turn(
        ud, "user", "raw stt text the model rewrote about debugging the sharded ledger consistency bug"
    )
    state.save_answer(
        ud,
        transcript="The model's curated answer for question one.",
        started_at="2026-06-08T09:00:00Z",
        ended_at="2026-06-08T09:01:30Z",
    )
    state.advance(ud)
    state.add_turn(
        ud, "user", "speech for question two that was never saved about migrating the billing service"
    )

    added = state.reconstruct_answers(ud)

    # 已有有效答案的题目不应生成第二条恢复记录。
    assert added == 1
    q1_records = [a for a in ud.ctx.answers if a.question_id == q1.id]
    assert len(q1_records) == 1
    assert q1_records[0].transcript == "The model's curated answer for question one."

    # 验证最后记录优先索引仍读取已保存答案，恢复记录只追加未保存的题。
    assert [a.question_id for a in ud.ctx.answers] == [q1.id, "q_behavioral"]
    by_id = {a.question_id: a for a in ud.ctx.answers}
    assert by_id[q1.id].transcript.startswith("The model's curated")
    assert by_id["q_behavioral"].transcript == (
        "speech for question two that was never saved about migrating the billing service"
    )


def test_evaluate_difficulty_sees_recovered_answers() -> None:
    """恢复后的有效回答必须被难度计算读取，并满足最低内容门槛。"""
    ud = _userdata()
    section = state.current_section(ud)
    assert section is not None and section != "wrap"

    before = state.evaluate_difficulty(ud)
    assert before.answered_in_section == 0
    assert before.recommendation == "advance"

    state.add_turn(
        ud, "user", "I used Python with asyncio to rebuild the ingestion worker around batching."
    )
    assert state.reconstruct_answers(ud) == 1

    after = state.evaluate_difficulty(ud)
    assert after.answered_in_section == 1
    assert after.recommendation == "advance"


def test_reconstruct_answers_substance_gate_drops_small_talk() -> None:
    """问候等短发言不能恢复为答案，避免触发无依据的低分报告。"""
    ud = _userdata()
    state.add_turn(ud, "assistant", "Hi! I'll be running your mock interview today.")
    state.add_turn(ud, "user", "Hi, nice to meet you, I'm ready!")

    assert state.reconstruct_answers(ud) == 0
    assert ud.ctx.answers == []


def test_reconstruct_answers_substance_gate_boundary() -> None:
    """门槛按同题合并内容计算：十一词不恢复，补足十二词后恢复。"""
    eleven = "one two three four five six seven eight nine ten eleven"
    ud = _userdata()
    state.add_turn(ud, "user", eleven)
    assert state.reconstruct_answers(ud) == 0
    assert ud.ctx.answers == []

    # 同题后续片段可累计补足恢复门槛。
    state.add_turn(ud, "user", "twelve")
    assert state.reconstruct_answers(ud) == 1
    assert ud.ctx.answers[-1].transcript == f"{eleven} twelve"


def test_trailing_empty_save_answer_does_not_block_recovery() -> None:
    """末尾空答案按最后记录优先规则覆盖旧答案时，仍须从真实发言补回有效答案。"""
    ud = _userdata()
    q1 = state.current_question(ud)
    assert q1 is not None
    state.add_turn(
        ud, "user", "I rebuilt the payments retry queue and cut duplicate charges to zero."
    )
    state.save_answer(ud, transcript="A curated answer.", started_at="", ended_at="")
    # 末尾空记录会在最后记录优先索引中覆盖原答案，因此需补回真实发言。
    state.save_answer(ud, transcript="", started_at="", ended_at="")

    assert state.reconstruct_answers(ud) == 1
    by_id = {a.question_id: a for a in ud.ctx.answers}
    assert by_id[q1.id].transcript.startswith("I rebuilt the payments retry queue")


def test_reconstruct_answers_never_recovers_wrap_phase_speech() -> None:
    """计划结束后的告别发言题号为空，不能恢复成回答。"""
    ud = _userdata()
    ud.ctx.cursor = len(ud.ctx.plan.questions)
    state.add_turn(ud, "user", "Thanks, this was a great conversation, goodbye!")
    assert ud.transcript[-1]["question_id"] == ""

    assert state.reconstruct_answers(ud) == 0
    assert ud.ctx.answers == []


def test_chinese_answer_without_spaces_is_recovered() -> None:
    ud = _userdata()
    text = "我首先检查上游数据采集链路，然后核对指标口径并重新计算当天的活跃用户数。"
    state.add_turn(ud, "user", text)
    assert state.reconstruct_answers(ud) == 1
    assert ud.ctx.answers[0].transcript == text


def test_short_chinese_greeting_is_not_recovered() -> None:
    ud = _userdata()
    state.add_turn(ud, "user", "你好，我准备好了。")
    assert state.reconstruct_answers(ud) == 0
