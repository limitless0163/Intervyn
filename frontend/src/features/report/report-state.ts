import type { SessionView } from "@/types/session";

export type ReportState =
  "ready" | "empty" | "scoring" | "preparing" | "waiting" | "error";

/** The server page and client poller must agree about when a report is done. */
export function reportState(view: SessionView): ReportState {
  const answers = view.context?.answers.length ?? 0;
  const hasScores = (view.scorecard?.competency_scores.length ?? 0) > 0;
  if (
    view.status === "no_answers" ||
    (answers === 0 && !!view.scorecard && !hasScores)
  )
    return "empty";
  if (view.status === "error" || view.status === "rejected") return "error";
  if (view.scorecard && (hasScores || view.status === "complete"))
    return "ready";
  if (view.status === "complete") return "error";
  if (view.status === "prep") return "preparing";
  if (view.status === "scoring") return "scoring";
  return answers === 0 ? "waiting" : "scoring";
}
