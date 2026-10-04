import { describe, expect, it } from "vitest";
import { reportState } from "../../src/features/report/report-state";
import { interviewContext, scorecard, sessionView } from "./fixtures";

describe("report page states", () => {
  it.each([
    ["prep", "preparing"],
    ["ready", "waiting"],
    ["scoring", "scoring"],
    ["no_answers", "empty"],
    ["error", "error"],
    ["rejected", "error"],
    ["complete", "error"],
  ] as const)("renders %s without a report as %s", (status, expected) => {
    expect(reportState(sessionView({ status }))).toBe(expected);
  });

  it("keeps a completed real report ready", () => {
    expect(
      reportState(
        sessionView({
          status: "complete",
          context: interviewContext(),
          scorecard: scorecard(),
        }),
      ),
    ).toBe("ready");
  });

  it("offers scoring when recorded answers have no card yet", () => {
    expect(reportState(sessionView({ context: interviewContext() }))).toBe(
      "scoring",
    );
  });

  it.each(["no_answers", "error", "rejected"] as const)(
    "does not let a stale card hide %s",
    (status) => {
      expect(
        reportState(
          sessionView({
            status,
            context: interviewContext(),
            scorecard: scorecard(),
          }),
        ),
      ).toBe(status === "no_answers" ? "empty" : "error");
    },
  );

  it("renders legacy empty cards as empty, without showing fabricated zero scores", () => {
    const card = scorecard();
    card.competency_scores = [];
    expect(
      reportState(sessionView({ status: "complete", scorecard: card })),
    ).toBe("empty");
  });
});
