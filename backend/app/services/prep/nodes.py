"""准备图的异步节点只返回各自计算的增量字段，由 LangGraph 汇合。

依赖通过 partial 注入；各外部调用失败时保留有效降级数据及会话警告。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import ValidationError

from ...core.adapters.mock import build_mock
from ...core.logging import get_logger
from ...core.tracing import traced
from ...schemas.shared_models import (
    CandidateProfile,
    Citation,
    CompanyIntel,
    JobSpec,
    QuestionPlan,
)
from .cv_extract import extract_cv_text
from .gap import basic_gap_analysis, with_gap_narrative
from .prompts import (
    company_research_prompts,
    cv_analysis_prompts,
    gap_narrative_prompts,
    jd_analysis_prompts,
    language_name,
    question_planner_prompts,
)
from .state import PrepState

if TYPE_CHECKING:
    from ...dependencies.container import Deps

log = get_logger(__name__)


async def _mark(state: PrepState, deps: Deps, step: str) -> None:
    """尽力记录已知会话的完成步骤，进度写入失败不能中断准备流程。"""
    session_id = state.get("session_id")
    if not session_id:
        return
    try:
        await deps.repo.mark_progress(session_id, step)
    except Exception as exc:  # noqa: BLE001 - 进度写入失败不能中断准备
        log.warning("mark_progress(%s) failed (%s)", step, exc)


async def _warn(state: PrepState, deps: Deps, warnings: list[str]) -> None:
    """尽力保存输入质量或降级警告，写入失败不影响准备流程。"""
    session_id = state.get("session_id")
    if not session_id or not warnings:
        return
    try:
        await deps.repo.add_warnings(session_id, warnings)
    except Exception as exc:  # noqa: BLE001 - 警告写入失败不能中断准备
        log.warning("add_warnings failed (%s)", exc)


@traced("prep.fetch_cv")
async def fetch_cv(state: PrepState, deps: Deps) -> PrepState:
    """提取简历正文并保存警告；若 cv_text 键已存在，则不重复解析。

    空正文也视为已解析，避免重复警告和多模态费用；意外异常时保留原输入。
    """
    if "cv_text" in state:
        return {}
    req = state["req"]
    try:
        cv_text, warnings = await extract_cv_text(req.cv_url, deps)
    except Exception as exc:  # noqa: BLE001 - 提取异常时保留原输入
        log.warning("fetch_cv: extraction failed, using cv_url as text (%s)", exc)
        return {"cv_text": req.cv_url}
    if warnings:
        await _warn(state, deps, warnings)
    return {"cv_text": cv_text}


@traced("prep.cv_analysis")
async def cv_analysis(state: PrepState, deps: Deps) -> PrepState:
    """从简历正文提取候选人资料，调用失败时使用最小有效资料并记录警告。"""
    system, user = cv_analysis_prompts(state["cv_text"])
    try:
        candidate = await asyncio.wait_for(
            deps.llm.complete_json(system=system, user=user, schema=CandidateProfile),
            timeout=deps.settings.llm_call_timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - 分析失败时降级而不中断准备
        log.warning("cv_analysis failed, using minimal profile (%s)", exc)
        candidate = build_mock(CandidateProfile)
        await _warn(state, deps, ["Could not analyze the CV; used a minimal profile."])
    await _mark(state, deps, "cv_analysis")
    return {"candidate": candidate}


@traced("prep.jd_analysis")
async def jd_analysis(state: PrepState, deps: Deps) -> PrepState:
    """从职位正文提取岗位要求，调用失败时使用最小有效要求并记录警告。"""
    req = state["req"]
    system, user = jd_analysis_prompts(req.jd_text, req.company)
    try:
        job = await asyncio.wait_for(
            deps.llm.complete_json(system=system, user=user, schema=JobSpec),
            timeout=deps.settings.llm_call_timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - 分析失败时降级而不中断准备
        log.warning("jd_analysis failed, using minimal job spec (%s)", exc)
        job = build_mock(JobSpec)
        await _warn(
            state, deps, ["Could not analyze the job description; used a minimal spec."]
        )
    await _mark(state, deps, "jd_analysis")
    return {"job": job}


def _empty_company_intel(name: str) -> CompanyIntel:
    """生成契约有效的空公司资料，避免为无效公司名编造信息。"""
    return CompanyIntel(
        name=name or "Unknown",
        summary="",
        industry=None,
        tech_stack=[],
        values=[],
        interview_process=[],
        recent_news=[],
        citations=[],
    )


@traced("prep.company_research")
async def company_research(state: PrepState, deps: Deps) -> PrepState:
    """检索公司资料并由模型整理；公司名无效时跳过搜索及模型调用。"""
    req = state["req"]
    company = req.company

    if not state.get("company_ok", True):
        log.info("company_research: skipping for junk company %r", company)
        await _mark(state, deps, "company_research")
        return {"company": _empty_company_intel(company)}

    primary = req.language_mode.primary

    queries: list[tuple[str, str]] = [(f"{company} interview process", "en")]
    if primary != "en":
        localized = f"{company} interview process {language_name(primary)}"
        queries.append((localized, primary))

    async def search_one(query: str, lang: str):
        try:
            return await asyncio.wait_for(
                deps.search.search(query, lang=lang, max_results=4),
                timeout=deps.settings.search_call_timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001 - 搜索失败允许继续准备
            log.warning("company_research: search failed (%s)", type(exc).__name__)
            return []

    batches = await asyncio.gather(*(search_one(query, lang) for query, lang in queries))
    results = [result for batch in batches for result in batch]

    snippets = "\n".join(f"- {r.title}: {r.snippet}" for r in results) or "(no results)"
    system, user = company_research_prompts(company, snippets)
    try:
        intel = await asyncio.wait_for(
            deps.llm.complete_json(system=system, user=user, schema=CompanyIntel),
            timeout=deps.settings.llm_call_timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - 公司分析失败时降级
        log.warning("company_research failed, using minimal intel (%s)", exc)
        intel = _empty_company_intel(company)
        await _warn(
            state, deps, ["Could not research the company; proceeding without intel."]
        )

    citations = [
        Citation(title=r.title, url=r.url, snippet=r.snippet) for r in results
    ]
    intel = intel.model_copy(update={"citations": citations})
    await _mark(state, deps, "company_research")
    return {"company": intel}


@traced("prep.gap_matching")
async def gap_matching(state: PrepState, deps: Deps) -> PrepState:
    """先计算确定性差距字段，模型仅补充摘要，失败时保留原分析。"""
    gap = basic_gap_analysis(state["candidate"], state["job"])
    system, user = gap_narrative_prompts(state["candidate"], state["job"], gap)
    try:
        narrative = await asyncio.wait_for(
            deps.llm.complete_text(system=system, user=user),
            timeout=min(deps.settings.llm_call_timeout_sec, 30.0),
        )
        gap = with_gap_narrative(gap, narrative)
    except Exception as exc:  # noqa: BLE001 - 模型说明失败时保留代码分析
        log.warning(
            "gap narrative unavailable session=%s error=%s; retaining code-generated analysis",
            state.get("session_id"), type(exc).__name__,
        )
        if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
            reason = "The model request timed out."
        elif isinstance(exc, (ValidationError, ValueError)):
            reason = "The model returned no usable explanation."
        else:
            reason = "The model service request failed."
        await _warn(state, deps, [
            "The code-generated gap analysis is ready, but its AI explanation is unavailable. "
            + reason
        ])
    await _mark(state, deps, "gap_matching")
    return {"gap": gap}


# 只注入规划相关章节并设字符预算，防止技能库增长导致提示词失控。
_HINT_SECTIONS = frozenset({"round structure", "question bank", "signals", "pitfalls"})
_HINT_CHAR_BUDGET = 1500


def _extract_hint_sections(body_md: str) -> str:
    """按原顺序提取技能正文中与问题规划相关的二级标题章节。"""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in body_md.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            current = [] if title.lower() in _HINT_SECTIONS else None
            if current is not None:
                sections.append((title, current))
        elif current is not None:
            current.append(line)
    parts = [f"{title}:\n" + "\n".join(lines).strip() for title, lines in sections if lines]
    return "\n".join(p for p in parts if not p.endswith(":\n"))


def _skill_library_hint(
    company: str, role: str, level: str, skills_dir: str | None = None
) -> str:
    """提取匹配技能的来源、题库及评估提示并按字符预算截断。

    技能库缺失或检索失败时返回空字符串，不让准备流程依赖技能库可用性。
    """
    try:
        from ..skilllib.store import effective_confidence, find_relevant

        skills = find_relevant(skills_dir, company=company, role=role, level=level)
        if not skills:
            return ""
        blocks: list[str] = []
        for skill in skills:
            fm = skill.frontmatter
            header = (
                f"### {fm.company} · {fm.role} · {fm.level} "
                f"[{fm.status}; confidence {effective_confidence(fm):.2f} "
                f"from {fm.source_runs} run(s); verified {fm.last_verified}]"
            )
            extract = _extract_hint_sections(skill.body_md)
            blocks.append(f"{header}\n{extract}" if extract else header)
        hint = "\n\n".join(blocks)
        if len(hint) > _HINT_CHAR_BUDGET:
            hint = hint[:_HINT_CHAR_BUDGET].rsplit("\n", 1)[0] + "\n[truncated]"
        return hint
    except Exception:  # noqa: BLE001 - 技能检索失败时忽略附加资料
        return ""


@traced("prep.question_planner")
async def question_planner(state: PrepState, deps: Deps) -> PrepState:
    """汇合上游结果生成问题计划；失败时返回有效通用计划并强制保留请求的语言设置。"""
    req = state["req"]
    system, user = question_planner_prompts(
        candidate=state["candidate"],
        job=state["job"],
        company=state["company"],
        gap=state["gap"],
        language_mode=req.language_mode,
    )
    # 附加匹配的技能参考，供模型结合当前简历与职位调整计划。
    hint = _skill_library_hint(
        company=state["company"].name,
        role=state["job"].title,
        level=state["job"].seniority,
    )
    if hint:
        user = (
            f"{user}\n\n"
            "PLAYBOOK REFERENCE (from the interview skill library — adapt to THIS "
            "candidate and JD; prefer reusing its strongest questions over "
            "inventing near-duplicates, and never copy questions that don't fit "
            "the gap analysis):\n"
            f"{hint}"
        )
    try:
        plan = await asyncio.wait_for(
            deps.llm.complete_json(system=system, user=user, schema=QuestionPlan),
            timeout=deps.settings.llm_call_timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - 规划失败仍需返回契约有效的计划
        log.warning(
            "question_planner failed session=%s error=%s; using generic plan",
            state.get("session_id"), type(exc).__name__,
        )
        plan = build_mock(QuestionPlan)
        if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
            reason = "The model request timed out."
        elif isinstance(exc, (ValidationError, ValueError)):
            reason = "The model returned an invalid or incomplete question plan."
        else:
            reason = "The model service request failed."
        await _warn(
            state, deps, [f"Could not tailor the question plan; used a generic one. {reason}"]
        )
    # 使用请求中的语言设置，避免模型回显偏差改变语音路由。
    plan = plan.model_copy(update={"language_mode": req.language_mode})
    await _mark(state, deps, "question_planner")
    return {"plan": plan}
