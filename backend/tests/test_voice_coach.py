"""仅验证不依赖 LiveKit 的语音教练指令及弱项摘要，不启动教练角色或工作进程。"""

from __future__ import annotations

from app.schemas.shared_models import (
    CompetencyScore,
    LanguageReport,
    ScoreCard,
)
from app.services.coach.prompts import coach_agent_instructions
from app.services.live.state import weak_areas_summary


def _scorecard(weak: list[str]) -> ScoreCard:
    comp = [
        CompetencyScore(
            competency=c, score=1.5, evidence=f"Struggled with {c}.", level="weak"
        )
        for c in weak
    ]
    return ScoreCard(
        overall_score=1.5,
        competency_scores=comp,
        strengths=[],
        weaknesses=list(weak),
        weak_competencies=list(weak),
        model_answers=[],
        next_steps=[],
        language_report=LanguageReport(
            fluency_score=3.0,
            filler_word_count=2,
            clarity_score=3.0,
            code_switching_notes="",
            pronunciation_notes="",
            summary="ok",
        ),
        summary="test scorecard",
    )


def test_instructions_are_socratic_and_localized() -> None:
    text = coach_agent_instructions("Weak areas: System Design.", "vi")
    assert isinstance(text, str) and text
    assert "System Design" in text
    assert "vi" in text
    # 验证苏格拉底式引导，避免直接灌输示范答案。
    assert "question" in text.lower()


def test_weak_areas_summary_lists_weak_competencies() -> None:
    summary = weak_areas_summary(_scorecard(["System Design", "Leadership"]))
    assert "System Design" in summary
    assert "Leadership" in summary


def test_weak_areas_summary_handles_no_scorecard() -> None:
    summary = weak_areas_summary(None)
    assert isinstance(summary, str) and summary


def test_weak_areas_summary_handles_no_weak() -> None:
    summary = weak_areas_summary(_scorecard([]))
    assert isinstance(summary, str) and summary
