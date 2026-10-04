"""语音学习教练角色，需安装 livekit 扩展，由 worker_coach 延迟导入。

实时轮次只使用紧凑弱项摘要；知识检索及学习计划生成位于独立教练服务。
"""

from __future__ import annotations

from livekit.agents import Agent

from ..coach.prompts import coach_agent_instructions


class CoachAgent(Agent):
    """以苏格拉底式对话辅导候选人。

    weak_areas_summary 为预先生成的弱项摘要，lang 指定辅导主语言。
    """

    def __init__(self, *, weak_areas_summary: str, lang: str = "en") -> None:
        super().__init__(
            instructions=coach_agent_instructions(weak_areas_summary, lang),
        )
