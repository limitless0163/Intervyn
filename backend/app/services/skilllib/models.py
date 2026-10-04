"""技能及待审草稿模型；YAML 元数据对应 SCHEMA.md，正文为 Markdown。

last_verified 使用 ISO 日期字符串；存储层将 YAML 自动解析的 date 转回字符串。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SkillStatus = Literal["draft", "review", "promoted", "deprecated"]


class SkillFrontmatter(BaseModel):
    """对应技能文件 SCHEMA.md 的机器可读元数据。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    company: str
    role: str
    level: str
    competency: list[str] = Field(default_factory=list)
    version: int = 1
    source_runs: int = 0
    confidence: float = 0.3
    last_verified: str
    status: SkillStatus = "draft"


class Skill(BaseModel):
    """包含结构化元数据及 Markdown 正文的完整技能。"""

    model_config = ConfigDict(extra="forbid")

    frontmatter: SkillFrontmatter
    body_md: str


class SkillDraft(BaseModel):
    """从单次会话提出的待审草稿，发布前不属于正式技能库。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    target_skill_id: str
    frontmatter: SkillFrontmatter
    body_md: str
    source_session_id: str
    created_at: str
