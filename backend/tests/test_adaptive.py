"""通过最小状态替身验证难度启发式，不依赖 LiveKit、时钟或随机值。"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.live import state


def _q(qid: str, section: str, difficulty: int = 3) -> SimpleNamespace:
    return SimpleNamespace(id=qid, section=section, difficulty=difficulty)


def _a(question_id: str, transcript: str) -> SimpleNamespace:
    return SimpleNamespace(question_id=question_id, transcript=transcript)


def _ud(questions, answers, cursor) -> SimpleNamespace:
    """提供难度函数实际读取的状态字段，不依赖 LiveKit。"""
    plan = SimpleNamespace(questions=list(questions))
    ctx = SimpleNamespace(plan=plan, answers=list(answers), cursor=cursor)
    return SimpleNamespace(ctx=ctx, session_id="s_test", transcript=[])


def _words(n: int) -> str:
    return " ".join("word" for _ in range(n))


def test_thin_answers_recommend_easier() -> None:
    questions = [_q("q1", "technical", difficulty=3)]
    answers = [_a("q1", _words(3))]
    sig = state.evaluate_difficulty(_ud(questions, answers, cursor=0))
    assert sig.recommendation == "easier"
    assert sig.section == "technical"
    assert isinstance(sig.rationale, str) and sig.rationale


def test_rich_answers_recommend_harder() -> None:
    questions = [_q("q1", "technical", difficulty=2)]
    answers = [_a("q1", _words(120))]
    sig = state.evaluate_difficulty(_ud(questions, answers, cursor=0))
    assert sig.recommendation == "harder"


def test_rich_answers_at_max_difficulty_advance_not_harder() -> None:
    # 题目已在最高难度时，应建议推进而非继续加难。
    questions = [_q("q1", "technical", difficulty=5)]
    answers = [_a("q1", _words(120))]
    sig = state.evaluate_difficulty(_ud(questions, answers, cursor=0))
    assert sig.recommendation == "advance"


def test_section_fully_answered_recommends_advance() -> None:
    questions = [
        _q("q1", "technical", difficulty=3),
        _q("q2", "technical", difficulty=3),
        _q("q3", "coding", difficulty=3),
    ]
    answers = [_a("q1", _words(40)), _a("q2", _words(40))]
    sig = state.evaluate_difficulty(_ud(questions, answers, cursor=1))
    assert sig.recommendation == "advance"
    assert sig.section == "technical"


def test_no_answers_yet_is_neutral_advance() -> None:
    # 尚无回答时缺少调整依据，应保持计划。
    questions = [_q("q1", "technical", difficulty=3)]
    sig = state.evaluate_difficulty(_ud(questions, [], cursor=0))
    assert sig.recommendation == "advance"
    assert sig.answered_in_section == 0


def test_past_end_recommends_wrap() -> None:
    questions = [_q("q1", "technical", difficulty=3)]
    answers = [_a("q1", _words(40))]
    sig = state.evaluate_difficulty(_ud(questions, answers, cursor=5))
    assert sig.recommendation == "wrap"
    assert sig.section is None


def test_wrap_section_is_still_a_real_question() -> None:
    questions = [_q("q1", "wrap", difficulty=1)]
    answers = [_a("q1", _words(40))]
    sig = state.evaluate_difficulty(_ud(questions, answers, cursor=0))
    assert sig.recommendation == "advance"


def test_is_deterministic_across_repeated_calls() -> None:
    questions = [_q("q1", "technical", difficulty=2)]
    answers = [_a("q1", _words(120))]
    ud = _ud(questions, answers, cursor=0)
    first = state.evaluate_difficulty(ud)
    second = state.evaluate_difficulty(ud)
    assert first == second
    # 建议函数不得修改游标。
    assert ud.ctx.cursor == 0


def test_rationale_string_helper_matches_signal() -> None:
    questions = [_q("q1", "technical", difficulty=3)]
    answers = [_a("q1", _words(3))]
    ud = _ud(questions, answers, cursor=0)
    sig = state.evaluate_difficulty(ud)
    text = state.difficulty_hint(ud)
    assert sig.recommendation in text
    assert sig.rationale in text
