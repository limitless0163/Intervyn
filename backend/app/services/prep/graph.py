"""准备流程先并行分析简历、职位和公司，再汇合生成差距分析与问题计划。"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import PrepState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from ...dependencies.container import Deps


def build_prep_graph(deps: Deps) -> CompiledStateGraph:
    """将依赖绑定到节点，保留 LangGraph 所需的单一状态参数签名。"""
    graph: StateGraph = StateGraph(PrepState)

    graph.add_node("fetch_cv", partial(nodes.fetch_cv, deps=deps))
    graph.add_node("cv_analysis", partial(nodes.cv_analysis, deps=deps))
    graph.add_node("jd_analysis", partial(nodes.jd_analysis, deps=deps))
    graph.add_node("company_research", partial(nodes.company_research, deps=deps))
    graph.add_node("gap_matching", partial(nodes.gap_matching, deps=deps))
    graph.add_node("question_planner", partial(nodes.question_planner, deps=deps))

    graph.add_edge(START, "fetch_cv")
    graph.add_edge("fetch_cv", "cv_analysis")
    graph.add_edge(START, "jd_analysis")
    graph.add_edge(START, "company_research")

    # 列表起点形成汇合屏障，确保后续规划读取到三个分支的完整结果。
    graph.add_edge(["cv_analysis", "jd_analysis", "company_research"], "gap_matching")

    graph.add_edge("gap_matching", "question_planner")
    graph.add_edge("question_planner", END)

    return graph.compile()
