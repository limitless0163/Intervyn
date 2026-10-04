"""Regression tests for the real-LLM JSON response parser (no SDK / API key).

Pins the production bug found by the full-stack real-provider e2e: the question
planner — the largest schema, so the biggest real Gemini response — returned a
valid JSON object FOLLOWED BY extra data, which the old ``json.loads`` + greedy
``{.*}`` fallback rejected, silently falling back to the generic mock plan (every
interview asked one question titled "mock"). These tests run on the deterministic
mock plan shape, so they catch a regression in CI without any provider key.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.core.adapters.llm import _loads_json
from app.core.adapters.mock import build_mock
from app.schemas.shared_models import QuestionPlan


def test_loads_clean_object() -> None:
    assert _loads_json('{"a": 1}') == {"a": 1}


def test_loads_clean_array() -> None:
    assert _loads_json('[1, 2, 3]') == [1, 2, 3]


def test_loads_strips_json_fence() -> None:
    assert _loads_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _loads_json('```\n{"a": 1}\n```') == {"a": 1}


def test_loads_first_value_when_trailing_extra_data() -> None:
    """THE failure class: a complete object, then 'Extra data' json.loads rejects."""
    assert _loads_json('{"a": 1}\n{"b": 2}') == {"a": 1}
    assert _loads_json('{"a": 1}\n\nNote: hope this helps!') == {"a": 1}


def test_loads_object_after_leading_prose() -> None:
    assert _loads_json('Here is your JSON:\n{"a": 1}') == {"a": 1}


def test_question_plan_survives_trailing_extra_data() -> None:
    """A realistic QuestionPlan payload with a duplicate trailing object still
    validates to the FIRST (complete) plan — not a mock fallback."""
    plan = build_mock(QuestionPlan)
    payload = plan.model_dump_json() + '\n\n{"note": "duplicate emission"}'
    parsed = QuestionPlan.model_validate(_loads_json(payload))
    assert parsed.model_dump() == plan.model_dump()


# --- reasoning-block stripping (the local/Qwen3 path) -------------------------


def test_loads_json_strips_think_block() -> None:
    """A <think> block must be removed BEFORE the first-brace scan.

    Qwen3 via Ollama routinely emits its scratchpad inline in `content`. The
    tolerant parser below takes the FIRST '{' it finds, so a brace anywhere in
    that scratchpad would be decoded as the answer — yielding a valid-looking
    but wrong object, or a parse failure that drops the pipeline to the mock.
    """
    raw = '<think>Maybe {"decoy": 1} would work? No.</think>\n{"real": true}'
    assert _loads_json(raw) == {"real": True}


def test_loads_json_strips_unterminated_think_tail() -> None:
    """A reply cut off mid-thought has no closing tag; the tail is never JSON."""
    raw = '{"real": true}\n<think>now let me double check {"decoy": 2}'
    assert _loads_json(raw) == {"real": True}


def test_loads_json_think_block_is_case_and_tag_insensitive() -> None:
    assert _loads_json('<THINKING>{"decoy": 1}</THINKING>{"real": 1}') == {"real": 1}


def test_loads_json_leaves_cloud_responses_untouched() -> None:
    """No <think> tags means byte-identical behaviour for Gemini/OpenAI."""
    assert _loads_json('{"a": 1}') == {"a": 1}
    assert _loads_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_schema_aware_parser_skips_echoed_contract_before_plan() -> None:
    plan = build_mock(QuestionPlan)
    raw = "Contract:\n" + json.dumps(QuestionPlan.model_json_schema())
    raw += "\nActual answer:\n" + plan.model_dump_json()
    assert _loads_json(raw, QuestionPlan) == plan


def test_schema_aware_parser_does_not_decode_nested_defs() -> None:
    raw = "Contract:\n" + json.dumps(QuestionPlan.model_json_schema())
    with pytest.raises(ValidationError) as caught:
        _loads_json(raw, QuestionPlan)
    assert any(e["loc"] == ("$defs",) for e in caught.value.errors())


def test_schema_aware_parser_rejects_truncated_outer_value() -> None:
    nested = build_mock(QuestionPlan).model_dump_json()
    with pytest.raises(json.JSONDecodeError):
        _loads_json('{"unfinished": ' + nested, QuestionPlan)


def test_schema_aware_parser_accepts_fences_reasoning_and_trailing_text() -> None:
    plan = build_mock(QuestionPlan)
    raw = '<think>{"decoy": true}</think>\n```json\n'
    raw += plan.model_dump_json() + '\n```\n{"note": "done"}'
    assert _loads_json(raw, QuestionPlan) == plan
