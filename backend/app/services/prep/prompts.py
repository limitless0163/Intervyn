"""构造准备图各节点的英文系统提示词及用户载荷，返回 (system, user)。

问题计划要求本地化文本同时包含 en 和候选人的主语言，供后续语音流程使用。
"""

from __future__ import annotations

from ...schemas.shared_models import (
    CandidateProfile,
    CompanyIntel,
    GapAnalysis,
    JobSpec,
    LanguageMode,
    PrepRequest,
)

# 使用语言名称提示模型，避免仅传入难以理解的语言代码。
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "vi": "Vietnamese",
    "es": "Spanish",
    "zh": "Chinese",
    "hi": "Hindi",
    "id": "Indonesian",
    "pt": "Portuguese",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
}


def language_name(code: str) -> str:
    """将语言代码转换为显示名称；未配置映射时保留代码。"""
    return _LANGUAGE_NAMES.get(code, code)


def cv_analysis_prompts(cv_text: str) -> tuple[str, str]:
    """构造从简历正文提取候选人资料的提示词。"""
    system = (
        "You are a meticulous technical recruiter. Read the candidate's CV/resume "
        "text and extract a structured profile. Infer seniority from years of "
        "experience and scope of work. Be faithful to the source; do not invent "
        "employers, degrees, or skills that are not supported by the text. Keep "
        "summary_120w to roughly 120 words. Respond ONLY with the requested schema."
    )
    user = f"CANDIDATE CV / RESUME TEXT:\n{cv_text}"
    return system, user


def jd_analysis_prompts(jd_text: str, company: str) -> tuple[str, str]:
    """构造从职位正文提取岗位要求的提示词。"""
    system = (
        "You are a hiring manager. Parse the job description into a structured job "
        "spec: title, seniority, must-have vs nice-to-have requirements, core "
        "responsibilities, and the technology stack. Preserve the original text in "
        "raw_text. Do not fabricate requirements the description does not state. "
        "Respond ONLY with the requested schema."
    )
    user = f"TARGET COMPANY: {company}\n\nJOB DESCRIPTION:\n{jd_text}"
    return system, user


def company_research_prompts(company: str, snippets: str) -> tuple[str, str]:
    """构造依据搜索片段整理公司资料的提示词。"""
    system = (
        "You are an interview-prep researcher. Using ONLY the provided web search "
        "snippets, summarize what a candidate should know before interviewing: a "
        "short company summary, industry, likely technology stack, stated values, "
        "the typical interview process and stages, and any recent news. If a field "
        "is not supported by the snippets, leave its list empty rather than "
        "guessing. Respond ONLY with the requested schema."
    )
    user = f"COMPANY: {company}\n\nWEB SEARCH SNIPPETS:\n{snippets}"
    return system, user


def gap_narrative_prompts(
    candidate: CandidateProfile, job: JobSpec, gap: GapAnalysis,
) -> tuple[str, str]:
    """只请求差距文字说明，所有结构化字段已由代码确定。"""
    system = (
        "You are an interview strategist. Compare the candidate against the job "
        "requirements and explain the most useful interview considerations in "
        "one concise paragraph of ordinary text, about 120 words. The application "
        "has already computed skill-label matches; explain their limitations and "
        "suggest what to verify using the candidate's achievements and projects. "
        "A label match does not prove proficiency, and an unmatched requirement "
        "does not prove inability. Do not invent evidence. Return prose directly. "
        "You do not need to generate JSON, a schema, field names, or tool arguments."
    )
    user = (
        "CANDIDATE SUMMARY:\n"
        f"- name: {candidate.name}\n"
        f"- headline: {candidate.headline}\n"
        f"- seniority: {candidate.seniority} ({candidate.years_experience}y)\n"
        f"- skills: {', '.join(candidate.skills)}\n"
        f"- achievements: {'; '.join(candidate.achievements)}\n\n"
        f"- projects: {'; '.join(p.name + ': ' + p.description for p in candidate.projects)}\n\n"
        "JOB REQUIREMENTS:\n"
        f"- title: {job.title} at {job.company_name}\n"
        f"- seniority: {job.seniority}\n"
        f"- must_have: {', '.join(job.must_have)}\n"
        f"- nice_to_have: {', '.join(job.nice_to_have)}\n"
        f"- tech_stack: {', '.join(job.tech_stack)}\n"
        f"- responsibilities: {'; '.join(job.responsibilities)}\n\n"
        "CODE-GENERATED SKILL MATCHING:\n"
        f"- matched labels: {', '.join(gap.matched_skills)}\n"
        f"- requirements to verify: {', '.join(gap.missing_skills)}"
    )
    return system, user


def question_planner_prompts(
    candidate: CandidateProfile,
    job: JobSpec,
    company: CompanyIntel,
    gap: GapAnalysis,
    language_mode: LanguageMode,
) -> tuple[str, str]:
    """构造汇合候选人、岗位、公司及差距信息的问题规划提示词。"""
    primary = language_mode.primary
    primary_name = language_name(primary)
    also_localize = (
        ""
        if primary == "en"
        else (
            f" In addition to the required 'en' entry, also provide a '{primary}' "
            f"({primary_name}) translation for every question's text. "
            f"Use exactly the keys 'en' and '{primary}' in text; "
            "never use language names or regional codes such as zh-CN."
        )
    )
    mixed_note = (
        " The interview may code-switch between English and the primary language."
        if language_mode.mixed
        else ""
    )
    system = (
        "You are a senior interviewer designing a structured ~15 minute mock "
        "interview. Produce a question plan that:\n"
        "- Contains exactly 6 concise questions total; do not generate a large bank.\n"
        "- Orders sections across intro, behavioral, technical, coding, and wrap.\n"
        "- Follows a RISING difficulty curve scored 1-5 (start easy, ramp up).\n"
        "- Gives every question a target_competency drawn from the gap analysis "
        "(prioritise probe_targets and missing_skills).\n"
        "- Attaches a scoring rubric of 1-3 RubricItems per question whose weights "
        "sum to about 1.0.\n"
        "- Seeds at least one followup probe per question.\n"
        "- Sets time_budget_min to about 15 and language_mode as given.\n"
        "- Tailors questions to the candidate's background and the company's "
        "interview process and values.\n"
        f"Write each question's text with an 'en' entry.{also_localize}{mixed_note} "
        "Respond ONLY with the requested schema."
    )
    user = (
        f"TARGET ROLE: {job.title} ({job.seniority}) at {company.name}\n"
        f"PRIMARY LANGUAGE: {primary} ({primary_name}); mixed={language_mode.mixed}\n\n"
        "CANDIDATE:\n"
        f"- {candidate.headline}; {candidate.years_experience}y; "
        f"skills: {', '.join(candidate.skills)}\n\n"
        f"- achievements: {'; '.join(candidate.achievements[:5])}\n"
        f"- projects: {'; '.join(p.name + ': ' + p.description for p in candidate.projects[:3])}\n\n"
        "JOB REQUIREMENTS:\n"
        f"- must_have: {', '.join(job.must_have)}\n"
        f"- responsibilities: {'; '.join(job.responsibilities)}\n\n"
        "COMPANY INTERVIEW CONTEXT:\n"
        f"- values: {', '.join(company.values)}\n"
        f"- interview_process: {' -> '.join(company.interview_process)}\n"
        f"- tech_stack: {', '.join(company.tech_stack)}\n\n"
        "GAP ANALYSIS:\n"
        f"- strengths: {', '.join(gap.strengths)}\n"
        f"- gaps: {', '.join(gap.gaps)}\n"
        f"- probe_targets: {', '.join(gap.probe_targets)}\n"
        f"- missing_skills: {', '.join(gap.missing_skills)}\n"
        f"- analysis notes: {gap.summary}\n\n"
        "Design the plan now."
    )
    return system, user


def _job_user_payload(req: PrepRequest) -> str:
    """将公司名和职位正文组装成紧凑的模型输入。"""
    return f"TARGET COMPANY: {req.company}\n\nJOB DESCRIPTION:\n{req.jd_text}"
