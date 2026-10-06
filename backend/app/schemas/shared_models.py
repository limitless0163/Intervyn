"""镜像 frontend/packages/shared/src 的 Zod 契约，字段及注册表必须保持一致。

时间使用 ISO-8601 UTC 字符串；共享字段采用 snake_case，不直接使用 datetime 对象。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

LANGUAGES = ("en", "vi", "es", "zh", "hi", "id", "pt", "fr", "de", "ja")
Language = Literal["en", "vi", "es", "zh", "hi", "id", "pt", "fr", "de", "ja"]
Section = Literal["intro", "behavioral", "technical", "coding", "wrap"]
Seniority = Literal["intern", "junior", "mid", "senior", "staff", "principal"]
MasteryLevel = Literal["weak", "developing", "solid", "strong"]


def _validate_localized_text(v: dict[str, str]) -> dict[str, str]:
    if not isinstance(v, dict):
        raise ValueError("LocalizedText must be an object")  # noqa: TRY004 - Pydantic 校验器要求抛出 ValueError
    if not v.get("en"):
        raise ValueError("LocalizedText must include a non-empty 'en' entry")
    for k in v:
        if k not in LANGUAGES:
            raise ValueError(f"LocalizedText contains an unsupported language key: {k}")
    return v


LocalizedText = Annotated[dict[str, str], AfterValidator(_validate_localized_text)]


# 候选人。


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    tech: list[str]


class Education(BaseModel):
    model_config = ConfigDict(extra="forbid")
    institution: str
    degree: str
    field: str | None = None
    year: int | None = None


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    headline: str
    summary_120w: str
    years_experience: int
    seniority: Seniority
    skills: list[str]
    projects: list[Project]
    achievements: list[str]
    education: list[Education]
    spoken_languages: list[str]
    links: list[str] = Field(default_factory=list)


# 岗位。


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    company_name: str
    location: str | None = None
    seniority: Seniority
    must_have: list[str]
    nice_to_have: list[str]
    responsibilities: list[str]
    tech_stack: list[str]
    raw_text: str


# 公司。


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    url: str
    snippet: str | None = None


class CompanyIntel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    summary: str
    industry: str | None = None
    tech_stack: list[str]
    values: list[str]
    interview_process: list[str]
    recent_news: list[str]
    sources: list[Citation] = Field(default_factory=list)
    research_status: Literal["complete", "unavailable"] = "unavailable"
    research_error: Literal[
        "not_configured", "unsupported_provider", "no_sources", "timeout",
        "request_failed", "invalid_company", "invalid_response",
    ] | None = None
    search_suggestions: str | None = None


# 能力差距。


class GapAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strengths: list[str]
    gaps: list[str]
    probe_targets: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    summary: str


# 问题计划。


class RubricItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion: str
    weight: float
    description: str


class PlannedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    section: Section
    text: LocalizedText
    difficulty: int
    rubric: list[RubricItem]
    followups: list[str]
    target_competency: str


class LanguageMode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary: Language
    mixed: bool


class QuestionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections_order: list[Section]
    questions: list[PlannedQuestion]
    time_budget_min: int
    language_mode: LanguageMode


# 面试回答。


class AnswerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    transcript: str
    started_at: str
    ended_at: str
    duration_sec: float | None = None
    followups_asked: list[str] = Field(default_factory=list)


# 评分报告。


class CompetencyScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    competency: str
    score: float
    evidence: str
    level: MasteryLevel


class LanguageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fluency_score: float
    filler_word_count: int
    clarity_score: float
    code_switching_notes: str
    pronunciation_notes: str
    summary: str


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    answer: str


class ScoreCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_score: float
    competency_scores: list[CompetencyScore]
    strengths: list[str]
    weaknesses: list[str]
    weak_competencies: list[str]
    model_answers: list[ModelAnswer]
    next_steps: list[str]
    language_report: LanguageReport
    summary: str
    # 已回答题目占计划题目的比例，用于区分面试未完成与回答能力不足。
    # 未答题不计入总分和弱项；默认 1.0 兼容尚无此字段的历史报告。
    coverage_pct: float = 1.0


# 学习教练。


MasteryState = Literal["unseen", "learning", "shaky", "mastered"]


class StudyModule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    competency: str
    status: MasteryState
    est_min: int
    rationale: str


class StudyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modules: list[StudyModule]
    summary: str
    total_min: int


class CoachChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    query: str
    lang: Language


class CoachReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    citations: list[Citation]
    follow_ups: list[str]


# 面试上下文。


class InterviewContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    candidate: CandidateProfile
    job: JobSpec
    company: CompanyIntel
    gap: GapAnalysis
    plan: QuestionPlan
    cursor: int = 0
    answers: list[AnswerRecord] = Field(default_factory=list)
    scorecard: ScoreCard | None = None


# 语音房间。


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    identity: str
    name: str | None = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    url: str
    room: str


class RoomMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str


# API 请求与响应。


class PrepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cv_url: str
    jd_text: str
    company: str
    language_mode: LanguageMode
    # 可选 Supabase 用户 ID；持久化后用于报告页 RLS，离线路径可为空。
    user_id: str | None = None


class PrepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str


class ScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    scorecard: ScoreCard


class KbIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 知识分区键；开源免登录流程使用 session_id，并非用户身份凭据。
    store_key: str
    files: list[str]


class KbIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track_id: str


class KbQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 知识分区键；开源流程使用 session_id。
    store_key: str
    query: str
    lang: Language


class KbQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    citations: list[Citation]


# 与 frontend/packages/shared/src/registry.ts 中的 SCHEMAS 同步。

MODELS: dict[str, type[BaseModel]] = {
    "Project": Project,
    "Education": Education,
    "CandidateProfile": CandidateProfile,
    "JobSpec": JobSpec,
    "Citation": Citation,
    "CompanyIntel": CompanyIntel,
    "GapAnalysis": GapAnalysis,
    "RubricItem": RubricItem,
    "PlannedQuestion": PlannedQuestion,
    "LanguageMode": LanguageMode,
    "QuestionPlan": QuestionPlan,
    "AnswerRecord": AnswerRecord,
    "CompetencyScore": CompetencyScore,
    "LanguageReport": LanguageReport,
    "ModelAnswer": ModelAnswer,
    "ScoreCard": ScoreCard,
    "StudyModule": StudyModule,
    "StudyPlan": StudyPlan,
    "CoachChatRequest": CoachChatRequest,
    "CoachReply": CoachReply,
    "InterviewContext": InterviewContext,
    "TokenRequest": TokenRequest,
    "TokenResponse": TokenResponse,
    "RoomMetadata": RoomMetadata,
    "PrepRequest": PrepRequest,
    "PrepResponse": PrepResponse,
    "ScoreRequest": ScoreRequest,
    "ScoreResponse": ScoreResponse,
    "KbIngestRequest": KbIngestRequest,
    "KbIngestResponse": KbIngestResponse,
    "KbQueryRequest": KbQueryRequest,
    "KbQueryResponse": KbQueryResponse,
}
