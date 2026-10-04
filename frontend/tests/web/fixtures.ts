import { SAMPLE_INTERVIEW_CONTEXT } from "@intervyn/shared";
import { SAMPLE_SCORECARD } from "../../src/features/report/sample-scorecard";
import type { SessionView } from "../../src/types/session";

export function sessionView(overrides: Partial<SessionView> = {}): SessionView {
  return {
    session_id: "session-1",
    status: "ready",
    progress: [],
    prep_warnings: [],
    context: null,
    scorecard: null,
    ...overrides,
  };
}

export function interviewContext() {
  return structuredClone(SAMPLE_INTERVIEW_CONTEXT);
}

export function scorecard() {
  return structuredClone(SAMPLE_SCORECARD);
}
