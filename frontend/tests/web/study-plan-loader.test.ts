import { beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_SCORECARD } from "../../src/features/report/sample-scorecard";
import { SAMPLE_STUDY_PLAN } from "../../src/features/prep/sample-mastery";

vi.mock("server-only", () => ({}));
vi.mock("../../src/services/api", () => ({ requestCoachPlan: vi.fn() }));

import { requestCoachPlan } from "../../src/services/api";
import { StudyPlanLoader } from "../../src/components/prep/study-plan-loader";

const request = vi.mocked(requestCoachPlan);
const props = {
  scorecard: SAMPLE_SCORECARD,
  sessionId: "session-1",
  isSample: false,
};

beforeEach(() => {
  request.mockReset();
});

describe("streamed study plan", () => {
  it("shows preview modules immediately without contacting the agent", async () => {
    const result = await StudyPlanLoader({ ...props, isSample: true });
    expect(request).not.toHaveBeenCalled();
    expect(result.props.unavailable).toBe(false);
    expect(result.props.modules).toBeUndefined();
  });

  it("keeps the linked session and uses its personalized modules", async () => {
    request.mockResolvedValue({
      modules: SAMPLE_STUDY_PLAN,
      summary: "Study these gaps",
      total_min: 30,
    });
    const result = await StudyPlanLoader(props);
    expect(request).toHaveBeenCalledWith(SAMPLE_SCORECARD);
    expect(result.props).toMatchObject({
      modules: SAMPLE_STUDY_PLAN,
      weakAreas: SAMPLE_SCORECARD.weak_competencies,
      sessionId: "session-1",
      unavailable: false,
    });
  });

  it.each(["failed", "empty"])(
    "labels the sample fallback for a %s plan",
    async (outcome) => {
      if (outcome === "failed")
        request.mockRejectedValue(new Error("Agent offline"));
      else
        request.mockResolvedValue({ modules: [], summary: "", total_min: 0 });
      const result = await StudyPlanLoader(props);
      expect(result.props.unavailable).toBe(true);
      expect(result.props.modules).toBeUndefined();
    },
  );
});
