"""API 专用读取模型，不纳入 TypeScript/Pydantic 共享契约校验。

会话视图返回准备进度、输入警告、面试上下文及评分结果。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .shared_models import InterviewContext, ScoreCard

__all__ = ["PROGRESS_STEPS", "SessionStatus", "SessionView"]

# complete 表示评分完成；no_answers 表示无回答并跳过评分，避免生成误导性的零分报告。
SessionStatus = Literal[
    "scoring",
    "prep", "ready", "rejected", "error", "complete", "no_answers"
]

# 准备步骤的规范顺序；实际完成顺序可能受并行分支影响。
PROGRESS_STEPS: tuple[str, ...] = (
    "cv_analysis",
    "jd_analysis",
    "company_research",
    "gap_matching",
    "question_planner",
)


class SessionView(BaseModel):
    """供会话查询返回状态、准备进度及已生成的上下文和报告。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: SessionStatus
    progress: list[str] = Field(default_factory=list)
    prep_warnings: list[str] = Field(default_factory=list)
    context: InterviewContext | None = None
    # 评分完成后供网页通过 API 读取报告，支持没有 Supabase 的部署。
    scorecard: ScoreCard | None = None
