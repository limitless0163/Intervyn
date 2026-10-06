import { describe, expect, it } from "vitest";
import { prepStepStatus, SessionViewSchema } from "../../src/types/session";

describe("prep step outcomes", () => {
  it("does not equate a settled company step with successful research", () => {
    const progress = ["company_research"];
    expect(prepStepStatus("company_research", progress, undefined)).toBe(
      "finished",
    );
    expect(
      prepStepStatus("company_research", progress, {
        company_research: "unavailable",
      }),
    ).toBe("unavailable");
    expect(
      prepStepStatus("company_research", progress, {
        company_research: "skipped",
      }),
    ).toBe("skipped");
    expect(
      prepStepStatus("company_research", progress, {
        company_research: "complete",
      }),
    ).toBe("complete");
  });

  it("keeps parallel work running and dependent steps pending", () => {
    const statuses = {
      cv_analysis: "running",
      jd_analysis: "running",
      company_research: "running",
    } as const;
    for (const key of Object.keys(statuses)) {
      expect(prepStepStatus(key, [], statuses)).toBe("running");
    }
    expect(prepStepStatus("gap_matching", [], statuses)).toBe("pending");
  });

  it("preserves outcomes through the polling response contract", () => {
    const view = SessionViewSchema.parse({
      session_id: "test",
      status: "prep",
      progress: ["company_research"],
      prep_step_statuses: {
        company_research: "unavailable",
        cv_analysis: "running",
      },
      prep_warnings: [],
      context: null,
    });
    expect(view.prep_step_statuses?.company_research).toBe("unavailable");
  });
});
