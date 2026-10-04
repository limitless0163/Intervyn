"""Code-owned gap structure; optional model prose never supplies its fields."""

import re

from ...schemas.shared_models import CandidateProfile, GapAnalysis, JobSpec


def basic_gap_analysis(candidate: CandidateProfile, job: JobSpec) -> GapAnalysis:
    """Match explicit skill labels only; unverified requirements remain probes.

    Exact, case-insensitive matches cannot establish proficiency, and an
    unmatched requirement cannot establish inability. Avoid semantic guesses
    and exclude mock placeholders from upstream fallback profiles/specs.
    """
    def key(text: str) -> str:
        return " ".join(text.split()).casefold()

    skills = {key(s) for s in candidate.skills if key(s) not in {"", "mock"}}
    requirements_by_key = {}
    for requirement in [*job.must_have, *job.tech_stack]:
        label = key(requirement)
        if label not in {"", "mock"}:
            requirements_by_key.setdefault(label, requirement.strip())
    requirements = list(requirements_by_key.values())
    matched = [r for r in requirements if key(r) in skills]
    unverified = [r for r in requirements if key(r) not in skills]
    probes = unverified or matched or [
        r for r in job.responsibilities if key(r) not in {"", "mock"}
    ]
    return GapAnalysis(
        strengths=[f"Listed in the CV: {r}" for r in matched],
        gaps=[f"Not confirmed by basic CV skill matching: {r}" for r in unverified],
        probe_targets=probes,
        matched_skills=matched,
        missing_skills=unverified,
        summary=(
            "Code-generated skill-label matching. "
            f"{len(matched)} job requirements match explicit CV skills; "
            f"{len(unverified)} require verification. "
            "Unmatched requirements are not evidence of inability."
        ),
    )


def with_gap_narrative(gap: GapAnalysis, narrative: str) -> GapAnalysis:
    """Store prose as a string only; never interpret it as structured fields."""
    narrative = re.sub(
        r"<(think|thinking)>.*?</\1>", "", narrative, flags=re.DOTALL | re.IGNORECASE,
    )
    narrative = re.sub(
        r"<(think|thinking)>.*\Z", "", narrative, flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if not narrative:
        raise ValueError("empty_gap_narrative")
    # Bounded context for the downstream planner; the deterministic summary
    # always remains visible even if the model supplies a very long answer.
    return gap.model_copy(update={
        "summary": f"{gap.summary}\n\nInterview considerations: {narrative[:3000]}",
    })
