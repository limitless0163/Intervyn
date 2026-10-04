"""差距结构由代码计算；模型只能补充文字说明。"""

import re

from ...schemas.shared_models import CandidateProfile, GapAnalysis, JobSpec


def basic_gap_analysis(candidate: CandidateProfile, job: JobSpec) -> GapAnalysis:
    """仅按显式技能标签做忽略大小写的匹配，排除上游 mock 占位值。

    匹配不代表熟练，未匹配也不代表不会；未证实的要求应作为面试探查目标。
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
    """清除推理块后仅追加文字说明，不从模型正文提取或覆盖结构化字段。"""
    narrative = re.sub(
        r"<(think|thinking)>.*?</\1>", "", narrative, flags=re.DOTALL | re.IGNORECASE,
    )
    narrative = re.sub(
        r"<(think|thinking)>.*\Z", "", narrative, flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if not narrative:
        raise ValueError("empty_gap_narrative")
    # 限制模型补充长度，确保下游规划仍能看到代码生成的确定性摘要。
    return gap.model_copy(update={
        "summary": f"{gap.summary}\n\nInterview considerations: {narrative[:3000]}",
    })
