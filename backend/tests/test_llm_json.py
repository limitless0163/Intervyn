"""不依赖 SDK 或密钥，验证模型 JSON 解析对尾部数据及推理块的兼容。

有效计划后附加数据不应迫使规划回退到模拟结果。
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
    """完整顶层值后的附加数据不能导致解析拒绝。"""
    assert _loads_json('{"a": 1}\n{"b": 2}') == {"a": 1}
    assert _loads_json('{"a": 1}\n\nNote: hope this helps!') == {"a": 1}


def test_loads_object_after_leading_prose() -> None:
    assert _loads_json('Here is your JSON:\n{"a": 1}') == {"a": 1}


def test_question_plan_survives_trailing_extra_data() -> None:
    """重复尾部对象不能覆盖首个完整且有效的问题计划。"""
    plan = build_mock(QuestionPlan)
    payload = plan.model_dump_json() + '\n\n{"note": "duplicate emission"}'
    parsed = QuestionPlan.model_validate(_loads_json(payload))
    assert parsed.model_dump() == plan.model_dump()


def test_loads_json_strips_think_block() -> None:
    """必须先移除推理块，避免其中的 JSON 被当作最终回答。"""
    raw = '<think>Maybe {"decoy": 1} would work? No.</think>\n{"real": true}'
    assert _loads_json(raw) == {"real": True}


def test_loads_json_strips_unterminated_think_tail() -> None:
    """未闭合推理块视为截断，不能从其尾部提取回答。"""
    raw = '{"real": true}\n<think>now let me double check {"decoy": 2}'
    assert _loads_json(raw) == {"real": True}


def test_loads_json_think_block_is_case_and_tag_insensitive() -> None:
    assert _loads_json('<THINKING>{"decoy": 1}</THINKING>{"real": 1}') == {"real": 1}


def test_loads_json_leaves_cloud_responses_untouched() -> None:
    """没有推理标签时正常云端回答的解析结果保持一致。"""
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
