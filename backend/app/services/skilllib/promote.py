"""审核后将草稿发布到正式库，不自动调用。

相同公司、岗位及级别的技能合并去重并升级版本；写入前再次清除正文个人信息。
"""

from __future__ import annotations

from pathlib import Path

from .models import Skill, SkillFrontmatter
from .scrub import scrub_pii
from .store import DEFAULT_SKILLS_DIR, load_skill, save_skill, slugify

_CONFIDENCE_STEP = 0.1
_CONFIDENCE_CAP = 0.95
_QUESTION_BANK_HEADING = "## Question bank"


def _parse_draft(draft_path: str | Path) -> Skill:
    """将待审文件按正式技能的元数据及正文格式解析。"""
    return load_skill(draft_path)


def _extract_question_bank(body: str) -> list[str]:
    """提取 Question bank 章节的题目列表行。"""
    lines = body.splitlines()
    bank: list[str] = []
    in_section = False
    for line in lines:
        if line.strip().startswith("## "):
            in_section = line.strip() == _QUESTION_BANK_HEADING
            continue
        if in_section and line.strip().startswith("- "):
            bank.append(line.strip())
    return bank


def _merge_question_banks(existing_body: str, draft_body: str) -> str:
    """将草稿中新题目追加到既有题库，按完整列表行去重。"""
    existing = _extract_question_bank(existing_body)
    incoming = _extract_question_bank(draft_body)
    seen = set(existing)
    new_lines = [q for q in incoming if q not in seen]
    if not new_lines:
        return existing_body

    out_lines: list[str] = []
    inserted = False
    in_section = False
    for line in existing_body.splitlines():
        if line.strip().startswith("## "):
            # 退出题库章节前插入新增题目，避免落到下一章节。
            if in_section and not inserted:
                out_lines.extend(new_lines)
                inserted = True
            in_section = line.strip() == _QUESTION_BANK_HEADING
        out_lines.append(line)
    # 题库位于文末时仍需补入新增题目。
    if in_section and not inserted:
        out_lines.extend(new_lines)
        inserted = True
    return "\n".join(out_lines) + ("\n" if existing_body.endswith("\n") else "")


def _merge_frontmatter(
    existing: SkillFrontmatter, draft: SkillFrontmatter
) -> SkillFrontmatter:
    """升级版本、累加来源次数、提高置信度并合并能力标签。"""
    merged_competency = sorted(set(existing.competency) | set(draft.competency))
    new_confidence = min(_CONFIDENCE_CAP, round(existing.confidence + _CONFIDENCE_STEP, 4))
    return existing.model_copy(
        update={
            "version": existing.version + 1,
            "source_runs": existing.source_runs + max(1, draft.source_runs),
            "confidence": new_confidence,
            "competency": merged_competency,
            "last_verified": draft.last_verified,
            "status": "promoted",
        }
    )


def promote(
    draft_path: str | Path,
    skills_dir: str | Path | None = None,
) -> Path:
    """发布已审核草稿并返回写入路径；必须由审核流程显式调用。"""
    root = Path(skills_dir) if skills_dir is not None else DEFAULT_SKILLS_DIR
    draft = _parse_draft(draft_path)
    dfm = draft.frontmatter

    slug = slugify(company=dfm.company, role=dfm.role, level=dfm.level)
    target_path = root / f"{slug}.md"

    if target_path.exists():
        existing = load_skill(target_path)
        frontmatter = _merge_frontmatter(existing.frontmatter, dfm)
        body = _merge_question_banks(existing.body_md, draft.body_md)
    else:
        frontmatter = dfm.model_copy(update={"id": slug, "status": "promoted"})
        body = draft.body_md

    # 再次清除正文个人信息，避免待审期间新增内容绕过落盘前检查。
    body = scrub_pii(body, names=[])

    skill = Skill(frontmatter=frontmatter, body_md=body)
    return save_skill(skill, target_path)
