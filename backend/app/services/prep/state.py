"""准备图的增量状态；各分支写入不同字段，由 LangGraph 汇合。"""

from __future__ import annotations

from typing import TypedDict

from ...schemas.shared_models import (
    CandidateProfile,
    CompanyIntel,
    GapAnalysis,
    JobSpec,
    PrepRequest,
    QuestionPlan,
)


class PrepState(TypedDict, total=False):
    """字段可缺省，允许流程从请求开始，逐步补齐上下文。"""

    req: PrepRequest
    # 复用已创建的会话，供各节点写入进度。
    session_id: str
    # 公司名无效时跳过研究，避免生成无依据的公司信息。
    company_ok: bool
    cv_text: str
    candidate: CandidateProfile
    job: JobSpec
    company: CompanyIntel
    gap: GapAnalysis
    plan: QuestionPlan
