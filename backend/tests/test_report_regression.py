"""用离线状态机模拟面试，再经 API 验证结果回写、评分及会话视图的完整链路。

先恢复遗漏回答再判断是否有答案，防止真实发言因未调用工具而落入 no_answers；
测试与路由复用进程内仓库。
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.dependencies.container import Deps, build_deps
from app.main import create_app
from app.schemas.shared_models import (
    LanguageMode,
    PrepRequest,
    ScoreCard,
)
from app.services.live import state
from app.services.live.state import InterviewUserdata
from app.services.prep import run_prep

# 足量原话确保超过恢复门槛，避免恢复场景与短发言过滤混淆。
_SPOKEN_ANSWER = (
    "I led the incident response when our payments ledger started double-charging "
    "customers. I traced the bug to a race between the retry worker and the "
    "settlement job, added an idempotency key on every write, backfilled the "
    "corrupted rows, and wrote a regression test so the failure mode can never "
    "silently return."
)

_CURATED_ANSWER = "The model's curated answer for question one."


def _client() -> TestClient:
    return TestClient(create_app())


def _prep_userdata() -> tuple[Deps, InterviewUserdata]:
    """运行模拟准备流程，并将已就绪上下文包装为面试状态。"""
    deps = build_deps()
    req = PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary="en", mixed=False),
    )
    session_id = asyncio.run(run_prep(req, deps))
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None, "prep must yield a ready context"
    return deps, InterviewUserdata(ctx=ctx, session_id=ctx.session_id)


def _add_behavioral_question(ud: InterviewUserdata) -> None:
    """为单题模拟计划追加不同环节的问题，覆盖跨题恢复场景。"""
    first = ud.ctx.plan.questions[0]
    ud.ctx.plan.questions.append(
        first.model_copy(update={"id": "q_behavioral", "section": "behavioral"})
    )


def _post_live_result(
    client: TestClient, ud: InterviewUserdata, status: str | None = None
) -> None:
    """经 API 重放工作进程结果回写，并校验成功响应。"""
    payload: dict = {
        "context": ud.ctx.model_dump(mode="json"),
        "transcript": ud.transcript,
        "status": status,
    }
    resp = client.post(f"/api/session/{ud.session_id}/live-result", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}


def _post_score(client: TestClient, session_id: str) -> dict:
    resp = client.post("/api/score", json={"session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_view(client: TestClient, session_id: str) -> dict:
    resp = client.get(f"/api/session/{session_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _simulate_unsaved_interview(ud: InterviewUserdata) -> int:
    """仅记录真实发言，再按关闭回调的顺序恢复答案；返回恢复记录数。"""
    state.add_turn(ud, "assistant", "Tell me about a hard production bug you fixed.")
    state.add_turn(ud, "user", _SPOKEN_ANSWER)
    assert ud.ctx.answers == [], "precondition: the model never called save_answer"
    return state.reconstruct_answers(ud)


def test_happy_path_saved_answers_yields_complete_view_with_scorecard() -> None:
    """已保存答案经回写、评分后，视图须为 complete 且保留回答与成绩单。"""
    _deps, ud = _prep_userdata()
    client = _client()
    q1 = state.current_question(ud)
    assert q1 is not None

    state.add_turn(ud, "assistant", q1.text.get("en", "First question."))
    state.add_turn(ud, "user", _SPOKEN_ANSWER)
    state.save_answer(
        ud,
        transcript=_SPOKEN_ANSWER,
        started_at="2026-06-11T09:00:00Z",
        ended_at="2026-06-11T09:02:00Z",
    )

    _post_live_result(client, ud)
    _post_score(client, ud.session_id)

    view = _get_view(client, ud.session_id)
    assert view["status"] == "complete"
    sc = view["scorecard"]
    assert sc is not None
    assert isinstance(sc["overall_score"], (int, float))
    assert 0.0 <= sc["overall_score"] <= 5.0
    answers = view["context"]["answers"]
    assert len(answers) == 1
    assert answers[0]["question_id"] == q1.id
    assert answers[0]["transcript"] == _SPOKEN_ANSWER


def test_recovery_when_save_answer_never_called_still_reaches_complete() -> None:
    """有真实发言但未调用保存工具时，恢复答案后仍须生成报告。"""
    _deps, ud = _prep_userdata()
    client = _client()
    q1 = state.current_question(ud)
    assert q1 is not None

    recovered = _simulate_unsaved_interview(ud)
    assert recovered == 1
    assert ud.ctx.answers[0].question_id == q1.id
    assert ud.ctx.answers[0].transcript == _SPOKEN_ANSWER

    # 有回答时不写终态提示，交由评分流程决定最终状态。
    _post_live_result(client, ud)
    _post_score(client, ud.session_id)

    view = _get_view(client, ud.session_id)
    assert view["status"] == "complete"
    assert view["status"] != "no_answers"
    assert view["scorecard"] is not None
    assert view["scorecard"]["competency_scores"], "recovered answer must be scored"


def test_silent_call_stays_no_answers_and_score_does_not_fabricate() -> None:
    """没有候选人发言时保留 no_answers，后续手动评分也不能编造成绩单。"""
    deps, ud = _prep_userdata()
    client = _client()

    state.add_turn(ud, "assistant", "Tell me about a hard production bug you fixed.")
    state.add_turn(ud, "assistant", "Hello? Are you still there?")
    assert state.reconstruct_answers(ud) == 0
    assert ud.ctx.answers == []

    # 无回答时由工作进程回写 no_answers。
    _post_live_result(client, ud, status="no_answers")

    view = _get_view(client, ud.session_id)
    assert view["status"] == "no_answers"
    assert view["scorecard"] is None

    body = _post_score(client, ud.session_id)
    assert body["scorecard"]["competency_scores"] == []
    assert body["scorecard"]["overall_score"] == 0.0

    view = _get_view(client, ud.session_id)
    assert view["status"] == "no_answers"
    assert view["scorecard"] is None
    assert deps.repo._rows[ud.session_id].scorecard is None


def test_mixed_saved_and_recovered_answers_score_and_curated_q1_wins() -> None:
    """第一题已有保存答案、第二题仅有转写时，只恢复第二题并保留第一题原记录。"""
    _deps, ud = _prep_userdata()
    _add_behavioral_question(ud)
    client = _client()
    q1 = state.current_question(ud)
    assert q1 is not None

    # 第一题同时有足量转写与已存答案，专门验证恢复不会生成重复记录。
    state.add_turn(ud, "assistant", "First question.")
    state.add_turn(
        ud, "user", "raw stt text for question one with enough words to clear the substance gate"
    )
    state.save_answer(ud, transcript=_CURATED_ANSWER, started_at="", ended_at="")
    state.advance(ud)

    # 第二题仅有转写，模拟模型遗漏保存工具。
    state.add_turn(ud, "assistant", "Now a behavioral question.")
    state.add_turn(ud, "user", _SPOKEN_ANSWER)

    recovered = state.reconstruct_answers(ud)
    assert recovered == 1
    assert len(ud.ctx.answers) == 2
    assert ud.ctx.answers[0].transcript == _CURATED_ANSWER
    assert ud.ctx.answers[1].question_id == "q_behavioral"
    assert ud.ctx.answers[1].transcript == _SPOKEN_ANSWER

    # 评分使用最后记录优先索引，第一题必须仍指向已存答案而非转写副本。
    by_id = {a.question_id: a for a in ud.ctx.answers}
    assert by_id[q1.id].transcript == _CURATED_ANSWER

    _post_live_result(client, ud)
    _post_score(client, ud.session_id)

    view = _get_view(client, ud.session_id)
    assert view["status"] == "complete"
    sc = ScoreCard.model_validate(view["scorecard"])
    assert sc.coverage_pct == 1.0
    assert {ma.question_id for ma in sc.model_answers} == {q1.id, "q_behavioral"}


def test_tagged_transcript_roundtrips_through_live_result() -> None:
    """题号标记和原始转录经结果回写后须原样保留，保证后续恢复及审核依据可用。"""
    deps, ud = _prep_userdata()
    client = _client()
    q1 = state.current_question(ud)
    assert q1 is not None

    state.add_turn(ud, "assistant", "Tell me about a hard production bug you fixed.")
    state.add_turn(ud, "user", _SPOKEN_ANSWER)

    _post_live_result(client, ud)

    persisted = deps.repo._rows[ud.session_id].transcript
    assert persisted == ud.transcript
    assert all("question_id" in turn for turn in persisted)
    assert {turn["question_id"] for turn in persisted} == {q1.id}


def test_scoring_idempotent_after_recovery_returns_persisted_card() -> None:
    """已恢复并评分的会话再次评分时返回持久化成绩单，不重算或覆盖。"""
    deps, ud = _prep_userdata()
    client = _client()

    assert _simulate_unsaved_interview(ud) == 1
    _post_live_result(client, ud)

    first = _post_score(client, ud.session_id)
    second = _post_score(client, ud.session_id)

    assert second["scorecard"]["summary"] == first["scorecard"]["summary"]
    assert second["scorecard"] == first["scorecard"]
    persisted = ScoreCard.model_validate(deps.repo._rows[ud.session_id].scorecard)
    assert ScoreCard.model_validate(second["scorecard"]) == persisted
    assert _get_view(client, ud.session_id)["status"] == "complete"


def test_empty_saved_answer_does_not_block_recovery() -> None:
    """空的已保存答案不能阻止同题真实发言被恢复和评分。"""
    _deps, ud = _prep_userdata()
    client = _client()
    q1 = state.current_question(ud)
    assert q1 is not None

    state.save_answer(ud, transcript="", started_at="", ended_at="")
    state.add_turn(ud, "user", _SPOKEN_ANSWER)

    recovered = state.reconstruct_answers(ud)
    assert recovered == 1, "blank saved record must not suppress recovery"
    assert ud.ctx.answers[-1].question_id == q1.id
    assert ud.ctx.answers[-1].transcript == _SPOKEN_ANSWER

    _post_live_result(client, ud)
    _post_score(client, ud.session_id)
    view = _get_view(client, ud.session_id)
    assert view["status"] == "complete"
    assert view["scorecard"] is not None


def test_live_result_disallowed_status_complete_is_ignored() -> None:
    """结果回写只允许 no_answers 或 error 终态提示，不能凭 complete 跳过评分。"""
    deps, ud = _prep_userdata()
    client = _client()
    state.add_turn(ud, "user", _SPOKEN_ANSWER)

    _post_live_result(client, ud, status="complete")

    view = _get_view(client, ud.session_id)
    assert view["status"] == "ready", "disallowed hint must leave the status alone"
    assert view["scorecard"] is None
    assert deps.repo.get_status(ud.session_id) == "ready"


def test_live_result_garbage_status_is_not_persisted_and_view_stays_readable() -> None:
    """任意状态字符串不能进入存储，避免后续读取模型校验失败。"""
    deps, ud = _prep_userdata()
    client = _client()

    _post_live_result(client, ud, status="garbage")

    view = _get_view(client, ud.session_id)
    assert view["status"] == "ready"
    assert deps.repo.get_status(ud.session_id) == "ready"
    # 仅丢弃不允许的状态提示，上下文本身仍须回写。
    assert view["context"] is not None


def test_recovered_answer_reaches_report_as_answered_coverage() -> None:
    """恢复后的回答须计入覆盖率、示范答案及对应能力评分。"""
    _deps, ud = _prep_userdata()
    client = _client()
    q1 = state.current_question(ud)
    assert q1 is not None

    assert _simulate_unsaved_interview(ud) == 1
    _post_live_result(client, ud)
    _post_score(client, ud.session_id)

    view = _get_view(client, ud.session_id)
    assert view["status"] == "complete"
    sc = ScoreCard.model_validate(view["scorecard"])

    assert sc.coverage_pct == 1.0
    assert {ma.question_id for ma in sc.model_answers} == {q1.id}
    plan_competencies = {q.target_competency for q in ud.ctx.plan.questions}
    assert sc.competency_scores
    assert {cs.competency for cs in sc.competency_scores} <= plan_competencies
