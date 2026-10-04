"""独立侧车内镜像共享知识契约，snake_case 字段须与前端及智能体保持一致。

侧车不导入主智能体包，HTTP 客户端仍可按共享 Citation 模型解析返回结果。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Language = Literal["en", "vi", "es", "zh", "hi", "id", "pt", "fr", "de", "ja"]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    url: str
    snippet: str | None = None


class KbIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    files: list[str]


class KbIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track_id: str


class KbQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    query: str
    lang: Language


class KbQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    citations: list[Citation]
