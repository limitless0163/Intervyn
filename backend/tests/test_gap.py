"""Gap failures must leave grounded probes and a visible, useful warning."""

import asyncio

import pytest

from app.core.adapters.mock import build_mock
from app.dependencies.container import build_deps
from app.repositories.repository import MemoryRepository
from app.schemas.shared_models import CandidateProfile, JobSpec, LanguageMode, PrepRequest
from app.services.prep.gap import basic_gap_analysis, with_gap_narrative
from app.services.prep.nodes import gap_matching


def sources():
    candidate = build_mock(CandidateProfile).model_copy(update={"skills": ["python", "SQL"]})
    job = build_mock(JobSpec).model_copy(update={
        "must_have": ["Python", "Distributed systems", "SQL"],
        "tech_stack": ["Python", "Go"], "responsibilities": ["Build payment APIs"],
    })
    return candidate, job


def test_basic_matching_preserves_unverified_requirements_as_probes():
    candidate, job = sources()
    gap = basic_gap_analysis(candidate, job)
    assert gap.matched_skills == ["Python", "SQL"]
    assert gap.missing_skills == ["Distributed systems", "Go"]
    assert gap.probe_targets == gap.missing_skills
    assert "not evidence of inability" in gap.summary
    assert "mock" not in gap.model_dump_json()


def test_basic_matching_does_not_match_substrings_or_fabricate_mock_evidence():
    candidate, job = sources()
    candidate.skills = ["JavaScript", "mock"]
    job.must_have = ["Java"]
    job.tech_stack = ["mock"]
    gap = basic_gap_analysis(candidate, job)
    assert gap.matched_skills == []
    assert gap.missing_skills == ["Java"]
    assert gap.strengths == []
    assert "mock" not in gap.model_dump_json()


def test_basic_matching_uses_responsibilities_when_no_skill_requirements():
    candidate, job = sources()
    job.must_have = job.tech_stack = []
    assert basic_gap_analysis(candidate, job).probe_targets == ["Build payment APIs"]


@pytest.mark.parametrize("error, reason", [
    (TimeoutError(), "timed out"),
    (ValueError("bad output"), "no usable explanation"),
    (RuntimeError("provider down"), "service request failed"),
])
def test_gap_failure_is_grounded_marks_progress_and_explains_cause(monkeypatch, error, reason):
    candidate, job = sources()
    deps = build_deps()
    monkeypatch.setattr(deps, "repo", MemoryRepository())

    class FailingLLM:
        async def complete_text(self, **kwargs):
            raise error

        async def complete_json(self, **kwargs):
            pytest.fail("GapAnalysis must never be requested from the model")

    monkeypatch.setattr(deps, "llm", FailingLLM())

    async def exercise():
        req = PrepRequest(
            cv_url="CV", jd_text="JD", company="Company",
            language_mode=LanguageMode(primary="en", mixed=False),
        )
        sid = await deps.repo.create_session(req)
        result = await gap_matching({
            "session_id": sid, "candidate": candidate, "job": job,
        }, deps)
        return result["gap"], await deps.repo.get_session_view(sid)

    gap, view = asyncio.run(exercise())
    assert gap == basic_gap_analysis(candidate, job)
    assert view.progress == ["gap_matching"]
    assert len(view.prep_warnings) == 1
    assert "code-generated gap analysis is ready" in view.prep_warnings[0]
    assert reason in view.prep_warnings[0]


def test_model_prose_never_controls_gap_fields(monkeypatch):
    candidate, job = sources()
    deps = build_deps()
    calls = []
    # Even text that looks like malformed structured output is only a string.
    narrative = '{"missing_skills": [[[["invented"]]]], "summary": '

    class ProseLLM:
        async def complete_text(self, **kwargs):
            calls.append(kwargs)
            return narrative

        async def complete_json(self, **kwargs):
            pytest.fail("GapAnalysis must never be requested from the model")

    monkeypatch.setattr(deps, "llm", ProseLLM())
    result = asyncio.run(gap_matching({"candidate": candidate, "job": job}, deps))["gap"]
    baseline = basic_gap_analysis(candidate, job)
    assert result.model_dump(exclude={"summary"}) == baseline.model_dump(exclude={"summary"})
    assert narrative.strip() in result.summary
    assert len(calls) == 1
    assert "Return prose directly" in calls[0]["system"]


def test_narrative_keeps_code_summary_and_discards_reasoning():
    gap = basic_gap_analysis(*sources())
    result = with_gap_narrative(gap, "<think>private scratchpad</think>Verify project scope.")
    assert result.summary.startswith(gap.summary)
    assert "Verify project scope." in result.summary
    assert "private scratchpad" not in result.summary
    with pytest.raises(ValueError):
        with_gap_narrative(gap, "<think>unfinished reasoning")


def test_requirements_are_deduplicated_case_insensitively():
    candidate, job = sources()
    job.must_have = [" Python ", "PYTHON"]
    job.tech_stack = ["python"]
    assert basic_gap_analysis(candidate, job).matched_skills == ["Python"]


def test_optional_narrative_timeout_keeps_structured_analysis(monkeypatch):
    candidate, job = sources()
    deps = build_deps()
    monkeypatch.setattr(deps.settings, "llm_call_timeout_sec", 0.01)
    cancelled = []

    class SlowLLM:
        async def complete_text(self, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

    monkeypatch.setattr(deps, "llm", SlowLLM())
    result = asyncio.run(gap_matching({"candidate": candidate, "job": job}, deps))
    assert result["gap"] == basic_gap_analysis(candidate, job)
    assert cancelled == [True]
