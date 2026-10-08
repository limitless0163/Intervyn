import "server-only";
import * as React from "react";
import type { ScoreCard, StudyModule } from "@intervyn/shared";
import { requestCoachPlan } from "@/services/api";
import { StudyPlan } from "./study-plan";

/** Stream the slow coach request independently from the usable prep tools. */
export async function StudyPlanLoader({
  scorecard,
  sessionId,
  isSample,
}: {
  scorecard: ScoreCard;
  sessionId: string | null;
  isSample: boolean;
}) {
  let modules: StudyModule[] | undefined;
  if (!isSample) {
    try {
      const plan = await requestCoachPlan(scorecard);
      if (plan.modules.length) modules = plan.modules;
    } catch {
      // Preserve offline use, and label sample content if a real request fails.
    }
  }
  return (
    <StudyPlan
      modules={modules}
      weakAreas={scorecard.weak_competencies}
      sessionId={sessionId}
      unavailable={!isSample && !modules}
    />
  );
}
