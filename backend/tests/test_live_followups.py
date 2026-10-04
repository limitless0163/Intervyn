"""Follow-up state regressions that run without the optional voice SDK."""

from types import SimpleNamespace

import pytest

from app.services.live import state


@pytest.fixture
def userdata():
    ctx = SimpleNamespace(
        cursor=0,
        answers=[],
        plan=SimpleNamespace(questions=[SimpleNamespace(id="q1"), SimpleNamespace(id="q2")]),
    )
    return state.InterviewUserdata(ctx=ctx, session_id="followup-test")


def test_followup_requires_an_initial_candidate_answer(userdata):
    state.add_turn(userdata, "assistant", "What did you build?")
    assert not state.mark_followup_pending(userdata)
    assert not state.followup_was_asked(userdata)


def test_followup_waits_for_a_new_candidate_turn(userdata):
    state.add_turn(userdata, "user", "I built a payments ledger.")
    assert state.mark_followup_pending(userdata)
    state.add_turn(userdata, "assistant", "How did you prevent duplicate charges?")
    # Repeated marking must not consume the original answer as the reply.
    assert state.mark_followup_pending(userdata)
    assert state.followup_is_pending(userdata)

    state.add_turn(userdata, "user", "I used idempotency keys.")
    assert not state.followup_is_pending(userdata)
    assert state.followup_was_asked(userdata)
    assert state.spoken_answer(userdata) == (
        "I built a payments ledger. I used idempotency keys."
    )


@pytest.mark.parametrize("empty_reply", ["", "   ", "\n\t"])
def test_empty_transcript_does_not_answer_a_followup(userdata, empty_reply):
    state.add_turn(userdata, "user", "I built a payments ledger.")
    state.mark_followup_pending(userdata)
    state.add_turn(userdata, "user", empty_reply)
    assert state.followup_is_pending(userdata)
    state.add_turn(userdata, "user", "I used idempotency keys.")
    assert not state.followup_is_pending(userdata)


@pytest.mark.parametrize("cursor", [1, 2])
def test_stale_followup_does_not_strand_recovered_cursor(userdata, cursor):
    state.add_turn(userdata, "user", "I built a payments ledger.")
    state.mark_followup_pending(userdata)
    userdata.ctx.cursor = cursor
    assert not state.followup_is_pending(userdata)
    assert not state.followup_was_asked(userdata)


def test_new_question_and_new_session_do_not_inherit_followup_history(userdata):
    state.add_turn(userdata, "user", "I built a payments ledger.")
    state.mark_followup_pending(userdata)
    state.add_turn(userdata, "user", "I used idempotency keys.")
    state.advance(userdata)
    assert not state.mark_followup_pending(userdata)
    state.add_turn(userdata, "user", "I mentored two engineers.")
    assert state.mark_followup_pending(userdata)
    assert state.followup_is_pending(userdata)
    other = state.InterviewUserdata(ctx=userdata.ctx, session_id="another-session")
    assert not state.followup_was_asked(other)
    assert not state.followup_is_pending(other)
