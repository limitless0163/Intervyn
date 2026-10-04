"""无密钥、无网络复现 MiniMax 准备阶段的结构化输出边界。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core.adapters.llm import MiniMaxLLM, _tool_schema
from app.core.adapters.mock import build_mock
from app.schemas.shared_models import CandidateProfile, GapAnalysis, JobSpec, QuestionPlan


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.closed = False
        self.chat = SimpleNamespace(completions=self)

    def with_options(self, **options):
        self.options = options
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def close(self):
        self.closed = True


def response(content, finish_reason="stop", tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish_reason,
    )])


def run(monkeypatch, replies, model="MiniMax-M3"):
    client = FakeClient(replies)
    llm = MiniMaxLLM("test", model)
    monkeypatch.setattr(llm, "_client", lambda: client)
    result = asyncio.run(llm.complete_json(system="s", user="u", schema=QuestionPlan))
    return result, client


def test_retries_schema_echo_with_field_feedback(monkeypatch):
    plan = build_mock(QuestionPlan)
    result, client = run(monkeypatch, [
        response(json.dumps(QuestionPlan.model_json_schema())),
        response(plan.model_dump_json()),
    ])
    assert result == plan
    assert len(client.calls) == 2
    assert "sections_order" in client.calls[1]["messages"][0]["content"]
    assert "not a JSON Schema" in client.calls[1]["messages"][0]["content"]
    assert client.calls[0]["extra_body"] == {
        "reasoning_split": True, "thinking": {"type": "disabled"},
    }
    assert "response_format" not in client.calls[0]
    assert client.calls[0]["temperature"] == 0.2
    tool = client.calls[0]["tools"][0]["function"]
    assert tool["name"] == "submit_result"
    assert tool["parameters"] == _tool_schema(QuestionPlan)
    assert client.options == {"max_retries": 0, "timeout": 90.0}
    assert client.closed


def test_transient_timeout_is_retried(monkeypatch):
    plan = build_mock(QuestionPlan)
    result, client = run(monkeypatch, [TimeoutError(), response(plan.model_dump_json())])
    assert result == plan
    assert len(client.calls) == 2


def test_length_finish_is_retried_even_when_content_is_valid(monkeypatch):
    plan = build_mock(QuestionPlan)
    result, client = run(monkeypatch, [
        response(plan.model_dump_json(), "length"), response(plan.model_dump_json()),
    ])
    assert result == plan
    assert len(client.calls) == 2


@pytest.mark.parametrize("model", ["MiniMax-M2.7", "MiniMax-M3.1-Flash-Preview"])
def test_other_models_do_not_receive_unsupported_thinking_disable(monkeypatch, model):
    plan = build_mock(QuestionPlan)
    _, client = run(monkeypatch, [response(plan.model_dump_json())], model)
    assert client.calls[0]["extra_body"] == {"reasoning_split": True}


def test_exhausted_retries_raise_and_close_client(monkeypatch):
    client = FakeClient([TimeoutError(), TimeoutError()])
    llm = MiniMaxLLM("test", "MiniMax-M3")
    monkeypatch.setattr(llm, "_client", lambda: client)
    with pytest.raises(TimeoutError):
        asyncio.run(llm.complete_json(system="s", user="u", schema=QuestionPlan))
    assert len(client.calls) == 2
    assert client.closed


def test_authentication_failure_is_not_retried(monkeypatch):
    class AuthError(Exception):
        status_code = 401

    client = FakeClient([AuthError()])
    llm = MiniMaxLLM("test", "MiniMax-M3")
    monkeypatch.setattr(llm, "_client", lambda: client)
    with pytest.raises(AuthError):
        asyncio.run(llm.complete_json(system="s", user="u", schema=QuestionPlan))
    assert len(client.calls) == 1
    assert client.closed


@pytest.mark.parametrize("status", [429, 503])
def test_transient_service_error_backs_off_before_retry(monkeypatch, status):
    class ServiceError(Exception):
        status_code = status

    sleeps = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    plan = build_mock(QuestionPlan)
    result, client = run(monkeypatch, [ServiceError(), response(plan.model_dump_json())])
    assert result == plan and len(client.calls) == 2
    assert sleeps == [1]


def test_tool_arguments_are_validated_instead_of_commentary(monkeypatch):
    plan = build_mock(QuestionPlan)
    calls = [SimpleNamespace(function=SimpleNamespace(
        name="submit_result", arguments=plan.model_dump_json(),
    ))]
    result, client = run(monkeypatch, [response(
        json.dumps(QuestionPlan.model_json_schema()), "tool_calls", calls,
    )])
    assert result == plan and len(client.calls) == 1


def test_unexpected_tool_name_is_rejected_then_retried(monkeypatch):
    plan = build_mock(QuestionPlan)
    calls = [SimpleNamespace(function=SimpleNamespace(
        name="wrong_function", arguments=plan.model_dump_json(),
    ))]
    result, client = run(monkeypatch, [
        response(None, "tool_calls", calls), response(plan.model_dump_json()),
    ])
    assert result == plan and len(client.calls) == 2


def test_output_tool_inlines_nested_refs_and_exposes_localized_text_rules():
    contract = _tool_schema(QuestionPlan)
    serialized = json.dumps(contract)
    assert '"$defs"' not in serialized and '"$ref"' not in serialized
    question = contract["properties"]["questions"]["items"]["properties"]
    assert question["rubric"]["items"]["properties"]["weight"]["type"] == "number"
    assert question["followups"]["type"] == "array"
    assert question["text"]["required"] == ["en"]
    assert "zh" in question["text"]["properties"]
    assert question["text"]["additionalProperties"] is False
    assert _tool_schema(JobSpec)["properties"]["title"]["type"] == "string"


def test_recovers_nested_array_envelopes_without_rewriting_content(monkeypatch):
    plan = build_mock(QuestionPlan)
    data = plan.model_dump()
    question = data["questions"][0]
    question["rubric"] = {"item": question["rubric"]}
    question["followups"] = {"items": question["followups"]}
    result, client = run(monkeypatch, [response(json.dumps(data))])
    assert result == plan
    assert len(client.calls) == 1


def test_array_normalization_preserves_single_text_and_nested_project_tech():
    from app.core.adapters.llm import _loads_json

    gap = build_mock(GapAnalysis)
    data = gap.model_dump()
    data["strengths"] = gap.strengths[0]
    assert _loads_json(json.dumps(data), GapAnalysis, normalize_arrays=True) == gap

    candidate = build_mock(CandidateProfile)
    data = candidate.model_dump()
    data["projects"][0]["tech"] = {"item": data["projects"][0]["tech"]}
    assert _loads_json(json.dumps(data), CandidateProfile, normalize_arrays=True) == candidate


def test_array_normalization_never_fills_missing_fields():
    from pydantic import ValidationError

    from app.core.adapters.llm import _loads_json

    data = build_mock(GapAnalysis).model_dump()
    del data["gaps"]
    with pytest.raises(ValidationError):
        _loads_json(json.dumps(data), GapAnalysis, normalize_arrays=True)


def test_gap_nested_string_arrays_and_wrappers_preserve_source_order(monkeypatch):
    gap = GapAnalysis(
        strengths=["Python", "SQL"], gaps=["Go not evidenced"],
        probe_targets=["Distributed systems"], matched_skills=["Python"],
        missing_skills=["Go"], summary="Verify job requirements against the CV.",
    )
    data = gap.model_dump()
    data["strengths"] = [[[["Python"]]], {"items": [["SQL"]]}]
    data["gaps"] = {"item": [[["Go not evidenced"]]]}
    calls = [SimpleNamespace(function=SimpleNamespace(
        name="submit_result", arguments=json.dumps(data),
    ))]
    client = FakeClient([response(None, "tool_calls", calls)])
    llm = MiniMaxLLM("test", "MiniMax-M3")
    monkeypatch.setattr(llm, "_client", lambda: client)
    result = asyncio.run(llm.complete_json(system="s", user="u", schema=GapAnalysis))
    assert result == gap
    assert len(client.calls) == 1


@pytest.mark.parametrize("invalid", [
    [[{"missing_skills": {"summary": "misplaced"}}]], [[42]], [[None]],
])
def test_string_array_normalization_rejects_non_text_and_misplaced_fields(invalid):
    from pydantic import ValidationError

    from app.core.adapters.llm import _loads_json

    data = build_mock(GapAnalysis).model_dump()
    data["missing_skills"] = invalid
    with pytest.raises(ValidationError):
        _loads_json(json.dumps(data), GapAnalysis, normalize_arrays=True)


def test_gap_misplaced_summary_retries_instead_of_silently_inventing_it(monkeypatch):
    gap = build_mock(GapAnalysis)
    malformed = gap.model_dump()
    summary = malformed.pop("summary")
    malformed["missing_skills"] = [[[{
        "missing_skills": {"summary": summary},
    }]]]
    client = FakeClient([response(json.dumps(malformed)), response(gap.model_dump_json())])
    llm = MiniMaxLLM("test", "MiniMax-M3")
    monkeypatch.setattr(llm, "_client", lambda: client)
    result = asyncio.run(llm.complete_json(system="s", user="u", schema=GapAnalysis))
    assert result == gap
    assert len(client.calls) == 2
    retry_prompt = client.calls[1]["messages"][0]["content"]
    assert "summary: Field required" in retry_prompt


@pytest.mark.parametrize("model, thinking", [("MiniMax-M3", True), ("MiniMax-M2.7", False)])
def test_plain_text_has_no_structured_output_contract(monkeypatch, model, thinking):
    client = FakeClient([response("Verify distributed systems experience.")])
    llm = MiniMaxLLM("test", model)
    monkeypatch.setattr(llm, "_client", lambda: client)
    result = asyncio.run(llm.complete_text(system="s", user="u"))
    assert result == "Verify distributed systems experience."
    call = client.calls[0]
    assert not {"tools", "tool_choice", "response_format"} & call.keys()
    assert ("thinking" in call["extra_body"]) is thinking
    assert client.closed


def test_plain_text_cancellation_closes_client(monkeypatch):
    client = FakeClient([asyncio.CancelledError()])

    async def cancel(**kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(client, "create", cancel)
    llm = MiniMaxLLM("test", "MiniMax-M3")
    monkeypatch.setattr(llm, "_client", lambda: client)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(llm.complete_text(system="s", user="u"))
    assert client.closed
