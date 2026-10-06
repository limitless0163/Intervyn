"""准备流程负责校验输入、生成并保存上下文，通过会话状态报告后台执行结果。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ...core.tracing import add_event, start_trace
from ...schemas.shared_models import InterviewContext
from ...utils.validation import validate_prep_inputs
from .graph import build_prep_graph
from .nodes import fetch_cv

if TYPE_CHECKING:
    from ...dependencies.container import Deps
    from ...schemas.shared_models import PrepRequest

__all__ = ["build_prep_graph", "run_prep", "run_prep_for_session"]

log = get_logger(__name__)


async def _ingest_prep_materials(
    session_id: str,
    req: PrepRequest,
    cv_text: str,
    ctx: InterviewContext,
    deps: Deps,
) -> None:
    """按 session_id 入库准备材料，与教练检索使用相同键。

    知识服务失败仅记录日志，不使已完成的准备流程失败。
    """
    files: list[str] = []
    if cv_text and cv_text.strip():
        files.append(f"CANDIDATE CV\n\n{cv_text.strip()}")
    if req.jd_text and req.jd_text.strip():
        files.append(f"JOB DESCRIPTION — {req.company}\n\n{req.jd_text.strip()}")

    company = ctx.company
    intel_parts: list[str] = []
    if company.summary:
        intel_parts.append(company.summary)
    if company.tech_stack:
        intel_parts.append("Technology: " + ", ".join(company.tech_stack))
    if company.values:
        intel_parts.append("Values: " + ", ".join(company.values))
    if company.sources:
        intel_parts.append("Sources:\n" + "\n".join(
            f"- {source.title}: {source.url}" for source in company.sources
        ))
    if company.interview_process:
        intel_parts.append(
            "Interview process:\n- " + "\n- ".join(company.interview_process)
        )
    if company.recent_news:
        intel_parts.append("Recent news:\n- " + "\n- ".join(company.recent_news))
    if intel_parts:
        files.append(f"COMPANY INTEL — {company.name}\n\n" + "\n\n".join(intel_parts))

    if not files:
        return
    try:
        track_id = await asyncio.wait_for(deps.knowledge.ingest(session_id, files), timeout=60.0)
        log.info(
            "prep: ingested %d doc(s) into the knowledge store for session %s (track %s)",
            len(files),
            session_id,
            track_id,
        )
    except Exception as exc:  # noqa: BLE001 - 知识入库失败不能阻断准备
        log.warning("prep: knowledge ingest failed for session %s (%s)", session_id, exc)


async def run_prep(req: PrepRequest, deps: Deps) -> str:
    """创建会话并等待准备流程结束，返回 session_id；最终状态可能为 ready、rejected 或 error。"""
    session_id = await deps.repo.create_session(req)
    await run_prep_for_session(session_id, req, deps)
    return session_id


async def run_prep_for_session(
    session_id: str, req: PrepRequest, deps: Deps
) -> None:
    """为现有会话执行准备流程；无效输入标记 rejected，执行失败标记 error。

    先提取简历再校验；异常在内部记录，便于 API 将其作为后台任务执行。
    """
    # 校验与图执行共用追踪，便于定位拒绝原因和模型调用。
    with start_trace(
        "prep",
        session_id=session_id,
        metadata={"company": req.company, "primary": req.language_mode.primary},
    ):
        try:
            # 校验提取后的正文，避免把文件地址或二进制内容当作候选人资料。
            fetched = await fetch_cv({"req": req, "session_id": session_id}, deps)
            cv_text = fetched.get("cv_text", req.cv_url)

            ok, warnings = validate_prep_inputs(req, cv_text=cv_text)
            if warnings:
                await deps.repo.add_warnings(session_id, warnings)

            if not ok:
                # 两项材料均无有效内容时直接拒绝，避免无效模型调用。
                await deps.repo.update_status(session_id, "rejected")
                add_event("prep.rejected", {"warnings": len(warnings)})
                return

            # 公司名无效只跳过研究，仍可依据简历和职位准备面试。
            company_ok = not any("company name" in w for w in warnings)

            graph = build_prep_graph(deps)
            result = await graph.ainvoke(
                {
                    "req": req,
                    "session_id": session_id,
                    "cv_text": cv_text,
                    "company_ok": company_ok,
                }
            )

            ctx = InterviewContext(
                session_id=session_id,
                candidate=result["candidate"],
                job=result["job"],
                company=result["company"],
                gap=result["gap"],
                plan=result["plan"],
                cursor=0,
                answers=[],
                scorecard=None,
            )

            await deps.repo.save_context(session_id, ctx)
            await deps.repo.update_status(session_id, "ready")
            add_event("prep.ready", {"questions": len(ctx.plan.questions)})

            # 为后续教练问答提供依据；入库失败不阻断准备流程。
            await _ingest_prep_materials(session_id, req, cv_text, ctx, deps)
        except Exception:
            log.exception("run_prep_for_session(%s) failed", session_id)
            try:
                await deps.repo.update_status(session_id, "error")
            except Exception:  # noqa: BLE001 - 尽力记录失败状态
                log.warning("could not mark session %s as error", session_id)
