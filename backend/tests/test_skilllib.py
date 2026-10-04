"""离线验证技能读写、检索、去标识化、草稿提炼及发布合并。

所有写入使用临时目录，确保候选人资料和待审草稿不污染正式技能库。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from pathlib import Path

import pytest

from app.dependencies.container import build_deps
from app.schemas.shared_models import AnswerRecord, LanguageMode, PrepRequest
from app.services.prep import run_prep
from app.services.skilllib import (
    effective_confidence,
    find_relevant,
    load_skill,
    promote,
    propose_skill,
    save_skill,
    scrub_pii,
    slugify,
)
from app.services.skilllib.distiller import REVIEW_SUBDIR
from app.services.skilllib.models import Skill, SkillFrontmatter
from app.services.skilllib.store import DEFAULT_SKILLS_DIR

_CANDIDATE_NAME = "Jane Q. Doe"
_CANDIDATE_EMAIL = "jane.doe@personalmail.example"
_CANDIDATE_PHONE = "+1 (415) 555-0199"


def _request() -> PrepRequest:
    return PrepRequest(
        cv_url="https://example.com/cv.pdf",
        jd_text="Senior Backend Engineer building distributed payment systems in Python.",
        company="ExampleCorp",
        language_mode=LanguageMode(primary="en", mixed=False),
    )


def _sample_skill() -> Skill:
    fm = SkillFrontmatter(
        id="examplecorp-backend-engineer-senior",
        company="ExampleCorp",
        role="backend-engineer",
        level="senior",
        competency=["system-design", "communication"],
        version=2,
        source_runs=3,
        confidence=0.55,
        last_verified="2026-06-08",
        status="promoted",
    )
    body = (
        "# ExampleCorp — Senior Backend Engineer\n\n"
        "## Round structure\n1. Intro\n2. System design\n\n"
        "## Question bank\n"
        '- "Design a multi-region rate limiter." (technical, target: system-design)\n\n'
        "## Signals\n- Reasons about trade-offs explicitly.\n\n"
        "## Pitfalls\n- Jumps to code before clarifying requirements.\n"
    )
    return Skill(frontmatter=fm, body_md=body)


def test_store_round_trips_a_skill(tmp_path: Path) -> None:
    skill = _sample_skill()
    path = tmp_path / "examplecorp-backend-engineer-senior.md"
    save_skill(skill, path)

    loaded = load_skill(path)
    assert loaded.frontmatter == skill.frontmatter
    assert loaded.body_md.strip() == skill.body_md.strip()
    # YAML 自动解析日期后，模型字段仍须恢复为字符串。
    assert loaded.frontmatter.last_verified == "2026-06-08"
    assert isinstance(loaded.frontmatter.last_verified, str)


def test_find_relevant_matches_company_and_role_only(tmp_path: Path) -> None:
    save_skill(_sample_skill(), tmp_path / "examplecorp-backend-engineer-senior.md")
    other = _sample_skill().model_copy(deep=True)
    other.frontmatter.id = "othercorp-frontend-junior"
    other.frontmatter.company = "OtherCorp"
    other.frontmatter.role = "frontend-engineer"
    other.frontmatter.level = "junior"
    save_skill(other, tmp_path / "othercorp-frontend-junior.md")

    hits = find_relevant(tmp_path, company="ExampleCorp", role="backend-engineer")
    assert len(hits) == 1
    assert hits[0].frontmatter.company == "ExampleCorp"

    assert find_relevant(tmp_path, company="OtherCorp", role="backend-engineer") == []
    # 级别只影响排名，staff 查询仍可返回 senior 技能。
    staff_hits = find_relevant(
        tmp_path, company="ExampleCorp", role="backend-engineer", level="staff"
    )
    assert [h.frontmatter.level for h in staff_hits] == ["senior"]


def test_find_relevant_matches_jd_titles_and_generic_fallback(tmp_path: Path) -> None:
    """岗位标题须匹配技能标识，generic 技能可作为任意公司的回退。"""
    generic = _sample_skill().model_copy(deep=True)
    generic.frontmatter.id = "generic-backend-engineer-senior"
    generic.frontmatter.company = "generic"
    save_skill(generic, tmp_path / "generic-backend-engineer-senior.md")

    # 使用真实职位标题及公司名称，而非预先规范化标识。
    hits = find_relevant(tmp_path, company="Stripe", role="Senior Backend Engineer")
    assert [h.frontmatter.id for h in hits] == ["generic-backend-engineer-senior"]

    assert find_relevant(tmp_path, company="Stripe", role="Data Scientist") == []

    # 公司精确匹配优先于 generic 回退。
    exact = _sample_skill().model_copy(deep=True)
    exact.frontmatter.id = "stripe-backend-engineer-senior"
    exact.frontmatter.company = "Stripe"
    save_skill(exact, tmp_path / "stripe-backend-engineer-senior.md")
    hits = find_relevant(tmp_path, company="Stripe", role="Senior Backend Engineer")
    assert hits[0].frontmatter.id == "stripe-backend-engineer-senior"


def test_find_relevant_matches_alternate_title_spellings(tmp_path: Path) -> None:
    """Front End、Developer、Engineering 等等价岗位写法须检索到对应技能。"""
    frontend = _sample_skill().model_copy(deep=True)
    frontend.frontmatter.id = "generic-frontend-engineer-mid"
    frontend.frontmatter.company = "generic"
    frontend.frontmatter.role = "frontend-engineer"
    frontend.frontmatter.level = "mid"
    save_skill(frontend, tmp_path / "generic-frontend-engineer-mid.md")

    for title in ("Front End Engineer", "Frontend Developer", "Front-End Dev"):
        hits = find_relevant(tmp_path, company="Acme", role=title)
        assert [h.frontmatter.id for h in hits] == ["generic-frontend-engineer-mid"], title

    ml = _sample_skill().model_copy(deep=True)
    ml.frontmatter.id = "generic-machine-learning-engineer-senior"
    ml.frontmatter.company = "generic"
    ml.frontmatter.role = "machine-learning-engineer"
    save_skill(ml, tmp_path / "generic-machine-learning-engineer-senior.md")

    hits = find_relevant(tmp_path, company="Acme", role="Senior ML Engineer")
    assert [h.frontmatter.id for h in hits] == ["generic-machine-learning-engineer-senior"]


def test_role_token_expansion_does_not_match_unrelated_roles(tmp_path: Path) -> None:
    """同义词扩展只能覆盖同类岗位，不能让后端技能匹配到设计岗位。"""
    backend = _sample_skill().model_copy(deep=True)
    backend.frontmatter.id = "generic-backend-engineer-senior"
    backend.frontmatter.company = "generic"
    save_skill(backend, tmp_path / "generic-backend-engineer-senior.md")

    for title in ("Product Designer", "Sales Manager", "Data Scientist", "Frontend Engineer"):
        assert find_relevant(tmp_path, company="Acme", role=title) == [], title


def test_role_token_expansion_is_monotone() -> None:
    """等价词扩展不能破坏原有的角色词子集匹配关系。"""
    from app.services.skilllib.store import _role_tokens

    pairs = [
        ("backend-engineer", "Senior Backend Engineer"),
        ("software-engineer", "Software Engineer"),
        ("data-engineer", "Staff Data Engineer"),
        ("engineering-manager", "Engineering Manager, Platform"),
        ("site-reliability-engineer", "Site Reliability Engineer"),
    ]
    for slug, title in pairs:
        assert _role_tokens(slug) <= _role_tokens(title), (slug, title)


def test_find_relevant_ranks_status_then_decayed_confidence(tmp_path: Path) -> None:
    """状态优先于置信度，同状态再比较时间衰减后的置信度。"""
    draft = _sample_skill().model_copy(deep=True)
    draft.frontmatter.id = "generic-a"
    draft.frontmatter.company = "generic"
    draft.frontmatter.status = "draft"
    draft.frontmatter.confidence = 0.9
    save_skill(draft, tmp_path / "a.md")

    promoted = _sample_skill().model_copy(deep=True)
    promoted.frontmatter.id = "generic-b"
    promoted.frontmatter.company = "generic"
    promoted.frontmatter.status = "promoted"
    promoted.frontmatter.confidence = 0.4
    save_skill(promoted, tmp_path / "b.md")

    hits = find_relevant(tmp_path, company="Acme", role="Backend Engineer", limit=2)
    assert [h.frontmatter.id for h in hits] == ["generic-b", "generic-a"]

    # 同状态同原始置信度时，最近验证的技能排名更高。
    stale = _sample_skill().model_copy(deep=True)
    stale.frontmatter.id = "generic-stale"
    stale.frontmatter.company = "generic"
    stale.frontmatter.status = "promoted"
    stale.frontmatter.last_verified = "2020-01-01"
    save_skill(stale, tmp_path / "stale.md")
    fresh = _sample_skill().model_copy(deep=True)
    fresh.frontmatter.id = "generic-fresh"
    fresh.frontmatter.company = "generic"
    fresh.frontmatter.status = "promoted"
    fresh.frontmatter.last_verified = _dt.datetime.now(tz=_dt.UTC).date().isoformat()
    save_skill(fresh, tmp_path / "fresh.md")
    hits = find_relevant(tmp_path, company="Acme", role="Backend Engineer", limit=4)
    assert hits.index(next(h for h in hits if h.frontmatter.id == "generic-fresh")) < hits.index(
        next(h for h in hits if h.frontmatter.id == "generic-stale")
    )


def test_effective_confidence_halves_at_half_life() -> None:
    fm = _sample_skill().frontmatter.model_copy(
        update={"confidence": 0.8, "last_verified": "2026-01-01"}
    )
    today = _dt.date(2026, 6, 30)
    assert effective_confidence(fm, today=today) == pytest.approx(0.4, rel=1e-3)
    # 无效日期不衰减，也不能使检索失败。
    fm_bad = fm.model_copy(update={"last_verified": "unknown"})
    assert effective_confidence(fm_bad, today=today) == 0.8


def test_skill_hint_injects_question_bank_into_planner_context(tmp_path: Path) -> None:
    """问题规划参考须包含技能正文中的题库，不能只注入元数据。"""
    from app.services.prep.nodes import _skill_library_hint

    generic = _sample_skill().model_copy(deep=True)
    generic.frontmatter.id = "generic-backend-engineer-senior"
    generic.frontmatter.company = "generic"
    save_skill(generic, tmp_path / "generic.md")

    hint = _skill_library_hint(
        company="Stripe",
        role="Senior Backend Engineer",
        level="senior",
        skills_dir=str(tmp_path),
    )
    assert "Design a multi-region rate limiter." in hint
    assert "Jumps to code before clarifying requirements." in hint
    assert len(hint) <= 1600

    # 空技能库返回空参考，不应报错。
    assert _skill_library_hint(
        company="Stripe", role="X", level="senior", skills_dir=str(tmp_path / "none")
    ) == ""


def test_find_relevant_loads_committed_example() -> None:
    """提交的虚构示例须能解析并按公司和岗位检索。"""
    hits = find_relevant(DEFAULT_SKILLS_DIR, company="ExampleCorp", role="backend-engineer")
    ids = {h.frontmatter.id for h in hits}
    assert "examplecorp-backend-senior" in ids
    assert find_relevant(DEFAULT_SKILLS_DIR, company="Nope", role="nobody") == []


def test_scrub_pii_removes_name_email_and_phone() -> None:
    text = (
        f"{_CANDIDATE_NAME} answered well. Reach at {_CANDIDATE_EMAIL} "
        f"or call {_CANDIDATE_PHONE} anytime."
    )
    scrubbed = scrub_pii(text, names=[_CANDIDATE_NAME])

    assert "Jane" not in scrubbed
    assert _CANDIDATE_EMAIL not in scrubbed
    assert "555-0199" not in scrubbed
    assert "[candidate]" in scrubbed
    assert "[email]" in scrubbed
    assert "[phone]" in scrubbed
    assert scrub_pii(scrubbed, names=[_CANDIDATE_NAME]) == scrubbed


def _prepared_session_with_pii(deps) -> str:
    """准备会话后植入可辨识姓名和含联系方式的回答，供清理测试使用。"""
    session_id = asyncio.run(run_prep(_request(), deps))
    ctx = asyncio.run(deps.repo.load_context(session_id))
    assert ctx is not None
    # 使用可辨识姓名验证落盘前清理。
    ctx.candidate.name = _CANDIDATE_NAME
    questions = ctx.plan.questions
    assert questions
    ctx.answers.append(
        AnswerRecord(
            question_id=questions[0].id,
            transcript=(
                f"My name is {_CANDIDATE_NAME}, you can reach me at {_CANDIDATE_EMAIL} "
                f"or {_CANDIDATE_PHONE}. I designed a service with idempotent retries."
            ),
            started_at="2026-06-08T09:00:00Z",
            ended_at="2026-06-08T09:02:00Z",
            duration_sec=120.0,
        )
    )
    asyncio.run(deps.repo.save_context(session_id, ctx))
    return session_id


def test_propose_skill_writes_draft_to_review_only_and_scrubs_pii(tmp_path: Path) -> None:
    deps = build_deps()
    session_id = _prepared_session_with_pii(deps)

    draft = asyncio.run(propose_skill(session_id, deps, skills_dir=tmp_path))

    assert draft.frontmatter.status == "draft"
    assert draft.frontmatter.source_runs == 1
    assert 0.0 < draft.frontmatter.confidence <= 0.4
    assert draft.source_session_id == session_id

    # 草稿只能进入待审目录，不能写入正式库顶层。
    review_path = tmp_path / REVIEW_SUBDIR / f"{draft.id}.md"
    assert review_path.exists(), "draft must be written to the review queue"
    live_files = list(tmp_path.glob("*.md"))
    assert live_files == [], "propose_skill must NOT write into the live library root"

    assert "Jane" not in draft.body_md
    assert "[candidate]" in draft.body_md
    # 检查落盘内容，不能仅内存对象已清理。
    assert "Jane" not in review_path.read_text(encoding="utf-8")


def test_promote_creates_new_skill_with_promoted_status(tmp_path: Path) -> None:
    deps = build_deps()
    session_id = _prepared_session_with_pii(deps)
    draft = asyncio.run(propose_skill(session_id, deps, skills_dir=tmp_path))
    draft_path = tmp_path / REVIEW_SUBDIR / f"{draft.id}.md"

    out_path = promote(draft_path, skills_dir=tmp_path)

    assert out_path.exists()
    assert out_path.parent == tmp_path  # 发布后文件位于正式库顶层。
    promoted = load_skill(out_path)
    assert promoted.frontmatter.status == "promoted"
    assert promoted.frontmatter.id == slugify(
        company=draft.frontmatter.company,
        role=draft.frontmatter.role,
        level=draft.frontmatter.level,
    )
    # 正式发布前再次清理正文个人信息。
    assert "Jane" not in promoted.body_md


def test_promote_merges_and_bumps_version_when_skill_exists(tmp_path: Path) -> None:
    deps = build_deps()
    session_id = _prepared_session_with_pii(deps)
    draft = asyncio.run(propose_skill(session_id, deps, skills_dir=tmp_path))
    draft_path = tmp_path / REVIEW_SUBDIR / f"{draft.id}.md"

    # 预置相同标识技能，迫使发布进入合并分支。
    slug = slugify(
        company=draft.frontmatter.company,
        role=draft.frontmatter.role,
        level=draft.frontmatter.level,
    )
    existing = Skill(
        frontmatter=SkillFrontmatter(
            id=slug,
            company=draft.frontmatter.company,
            role=draft.frontmatter.role,
            level=draft.frontmatter.level,
            competency=["pre-existing-competency"],
            version=4,
            source_runs=9,
            confidence=0.6,
            last_verified="2026-01-01",
            status="promoted",
        ),
        body_md=(
            "# Existing\n\n## Question bank\n"
            '- "An already-known question." (technical, target: x)\n'
        ),
    )
    save_skill(existing, tmp_path / f"{slug}.md")

    out_path = promote(draft_path, skills_dir=tmp_path)
    merged = load_skill(out_path)

    assert merged.frontmatter.version == 5, "version must bump on merge"
    assert merged.frontmatter.source_runs == 10, "source_runs must increment"
    assert merged.frontmatter.confidence > 0.6, "confidence must rise modestly"
    assert merged.frontmatter.confidence <= 0.95
    assert merged.frontmatter.status == "promoted"
    # 合并须保留已有题目并去重新增题目。
    assert "An already-known question." in merged.body_md
    assert "Jane" not in merged.body_md


def test_propose_default_dir_writes_to_review_only(
    tmp_path: Path, monkeypatch
) -> None:
    """将默认目录替换为临时目录，覆盖未传 skills_dir 的路径且不触碰正式库。"""
    from app.services.skilllib import distiller as distiller_mod

    monkeypatch.setattr(distiller_mod, "DEFAULT_SKILLS_DIR", tmp_path)

    deps = build_deps()
    session_id = _prepared_session_with_pii(deps)
    draft = asyncio.run(propose_skill(session_id, deps))

    assert (tmp_path / REVIEW_SUBDIR / f"{draft.id}.md").exists()
    assert list(tmp_path.glob("*.md")) == [], "default branch must not write live skills"


def test_render_index_lists_packs_and_counts_questions(tmp_path: Path) -> None:
    from app.services.skilllib.gen_index import render_index

    save_skill(_sample_skill(), tmp_path / "examplecorp-backend-engineer-senior.md")
    table = render_index(tmp_path)
    assert "[examplecorp-backend-engineer-senior](./examplecorp-backend-engineer-senior.md)" in table
    assert "| 1 |" in table


def test_update_readme_replaces_only_marker_block(tmp_path: Path) -> None:
    from app.services.skilllib.gen_index import (
        END_MARKER,
        START_MARKER,
        update_readme,
    )

    save_skill(_sample_skill(), tmp_path / "examplecorp-backend-engineer-senior.md")
    readme = tmp_path / "README.md"
    readme.write_text(f"intro\n\n{START_MARKER}\nstale\n{END_MARKER}\n\noutro\n", encoding="utf-8")
    update_readme(tmp_path)
    text = readme.read_text(encoding="utf-8")
    assert "stale" not in text
    assert text.startswith("intro") and text.rstrip().endswith("outro")
    assert "| Pack |" in text

    # 缺失索引标记时明确失败，不能任意覆盖 README 内容。
    bare = tmp_path / "sub"
    bare.mkdir()
    (bare / "README.md").write_text("no markers", encoding="utf-8")
    with pytest.raises(SystemExit):
        update_readme(bare)
