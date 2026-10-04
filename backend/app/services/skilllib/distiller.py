"""从会话上下文和评分卡生成去标识化技能草稿，仅写入 backend/skills/_review。

题库来自计划中的全部问题，不据此判断题目是否实际问过；正式发布须另行审核。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from .models import SkillDraft, SkillFrontmatter
from .scrub import scrub_pii
from .store import DEFAULT_SKILLS_DIR, slugify

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import InterviewContext

REVIEW_SUBDIR = "_review"
_DEFAULT_CONFIDENCE = 0.3


def _session_date(ctx: InterviewContext) -> str:
    """使用首条回答的 ISO 日期；没有回答时使用当前 UTC 日期。"""
    if ctx.answers:
        return ctx.answers[0].started_at[:10]
    return datetime.now(UTC).date().isoformat()


def _question_text(q) -> str:
    return q.text.get("en") or next(iter(q.text.values()), "")


def _build_body(ctx: InterviewContext, narrative: str) -> str:
    """根据计划和评分卡组装技能正文；题库包含全部计划题目。

    来源说明含候选人姓名，调用方必须在落盘前执行 scrub_pii。
    """
    job = ctx.job
    plan = ctx.plan
    sc = ctx.scorecard

    title = f"{job.company_name} — {job.title} ({job.seniority})"

    rounds = "\n".join(
        f"{i}. {section.title()}" for i, section in enumerate(plan.sections_order, start=1)
    ) or "1. (no sections recorded)"

    # 题库保留计划顺序，包含未实际作答的计划题目。
    bank_lines = [f'- "{_question_text(q)}" ({q.section}, target: {q.target_competency})'
                  for q in plan.questions]
    question_bank = "\n".join(bank_lines) or "- (no questions recorded)"

    if sc is not None:
        signals = "\n".join(f"- {s}" for s in sc.strengths) or "- (none recorded)"
        pitfalls = "\n".join(f"- {w}" for w in sc.weaknesses) or "- (none recorded)"
        calibration = "\n".join(
            f"- {cs.competency}: observed level **{cs.level}** "
            f"(score {cs.score:.1f}) — {cs.evidence}"
            for cs in sc.competency_scores
        ) or "- (no competency scores recorded)"
    else:
        signals = "- (interview not yet scored)"
        pitfalls = "- (interview not yet scored)"
        calibration = "- (interview not yet scored)"

    provenance = (
        f"Distilled from 1 interview run with candidate {ctx.candidate.name} "
        f"(session {ctx.session_id})."
    )

    return (
        f"# {title}\n\n"
        f"> {provenance}\n\n"
        f"## Summary\n{narrative.strip()}\n\n"
        f"## Round structure\n{rounds}\n\n"
        f"## Question bank\n{question_bank}\n\n"
        f"## Signals\n{signals}\n\n"
        f"## Pitfalls\n{pitfalls}\n\n"
        f"## Rubric calibration\n{calibration}\n"
    )


async def propose_skill(
    session_id: str,
    deps: Deps,
    *,
    skills_dir: str | Path | None = None,
    date: str | None = None,
) -> SkillDraft:
    """读取会话、生成技能草稿并清除正文中的个人信息，只写待审目录。

    skills_dir 可指定技能库根目录，date 可覆盖验证日期；返回草稿但不自动发布。
    """
    ctx = await deps.repo.load_context(session_id)
    if ctx is None:
        raise KeyError(f"No persisted context for session_id: {session_id}")

    root = Path(skills_dir) if skills_dir is not None else DEFAULT_SKILLS_DIR
    review_dir = root / REVIEW_SUBDIR

    company = ctx.job.company_name
    role = ctx.job.title
    level = ctx.job.seniority
    target_skill_id = slugify(company=company, role=role, level=level)
    last_verified = date or _session_date(ctx)

    # 模型只生成简短叙述，结构字段从会话确定性推导。
    system = (
        "You are an interview-prep analyst. In 2-3 sentences, summarize the "
        "reusable, DE-IDENTIFIED takeaways from this interview for future "
        "candidates targeting the same company/role/level. Do not name the "
        "candidate or include any personal contact details."
    )
    user = (
        f"Company: {company}\nRole: {role} ({level})\n"
        f"Sections: {', '.join(ctx.plan.sections_order)}\n"
        f"Questions asked: {len(ctx.plan.questions)}\n"
    )
    narrative = await deps.llm.complete_text(system=system, user=user)

    body = _build_body(ctx, narrative)
    # 正文落盘前清除已知姓名和联系方式。
    body = scrub_pii(body, names=[ctx.candidate.name])

    competency = sorted({q.target_competency for q in ctx.plan.questions if q.target_competency})

    draft_id = f"draft_{slugify(company=company, role=role, level=level)}_{uuid4().hex[:8]}"
    frontmatter = SkillFrontmatter(
        id=target_skill_id,
        company=company,
        role=role,
        level=level,
        competency=competency,
        version=1,
        source_runs=1,
        confidence=_DEFAULT_CONFIDENCE,
        last_verified=last_verified,
        status="draft",
    )
    draft = SkillDraft(
        id=draft_id,
        target_skill_id=target_skill_id,
        frontmatter=frontmatter,
        body_md=body,
        source_session_id=session_id,
        created_at=datetime.now(UTC).isoformat(),
    )

    # 仅写待审目录，正式库发布必须经过独立审核。
    review_dir.mkdir(parents=True, exist_ok=True)
    draft_path = review_dir / f"{draft_id}.md"
    _write_draft(draft, draft_path)
    return draft


def _write_draft(draft: SkillDraft, path: Path) -> None:
    """将草稿转为带 YAML 元数据的技能文本，写入指定待审文件。"""
    from .models import Skill
    from .store import serialize_skill

    skill = Skill(frontmatter=draft.frontmatter, body_md=draft.body_md)
    path.write_text(serialize_skill(skill), encoding="utf-8")
