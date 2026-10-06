"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { Eyebrow } from "@/components/ui/eyebrow";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import {
  SAMPLE_MASTERY_GRAPH,
  type MasteryGraph,
  type MasteryState,
} from "@/features/prep/sample-mastery";
import { MASTERY_LABEL, MASTERY_COLORS } from "@/components/prep/status-chip";

const MasteryFlow = dynamic(
  () => import("./mastery-flow").then((module) => module.MasteryFlow),
  {
    ssr: false,
    loading: () => (
      <div className="h-full bg-line-2 motion-safe:animate-pulse" />
    ),
  },
);

/**
 * Read-only prerequisite map over the candidate's competency entities, colored
 * by mastery `state`. Calm, non-interactive (pan/zoom/selection off), fits the
 * editorial look. Fixed-height container — a zero-height parent renders nothing.
 */
export function MasteryGraphView({
  graph = SAMPLE_MASTERY_GRAPH,
}: {
  graph?: MasteryGraph;
}) {
  const messages = useMessages();
  const masteryLabels = useMemo<Record<MasteryState, string>>(
    () => ({
      unseen: t(messages, "prep.notStarted"),
      learning: t(messages, "prep.learning"),
      shaky: t(messages, "prep.shaky"),
      mastered: t(messages, "prep.mastered"),
    }),
    [messages],
  );

  return (
    <section className="min-w-0" aria-labelledby="mastery-heading">
      <header className="mb-4">
        <Eyebrow>{t(messages, "prep.knowledgeMap")}</Eyebrow>
        <h2
          id="mastery-heading"
          className="mt-2 font-sans font-semibold tracking-tight text-2xl text-ink"
        >
          {t(messages, "prep.masteryGraph")}
        </h2>
        <p className="mt-1 text-[14px] leading-relaxed text-muted">
          {t(messages, "prep.graphDescription")}
        </p>
      </header>

      <div
        className="h-[420px] w-full overflow-hidden rounded-card border border-line bg-panel"
        role="img"
        aria-label={t(messages, "prep.graphLabel")}
      >
        <MasteryFlow graph={graph} labels={masteryLabels} />
      </div>

      <ul className="sr-only" aria-label={t(messages, "prep.masteryGraph")}>
        {graph.nodes.map((node) => (
          <li key={node.id}>
            {node.label}: {masteryLabels[node.state]}
          </li>
        ))}
      </ul>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-3">
        {(Object.keys(MASTERY_LABEL) as MasteryState[]).map((s) => {
          const c = MASTERY_COLORS[s];
          return (
            <span
              key={s}
              className="inline-flex items-center gap-1.5 text-[12px] text-muted"
            >
              <span
                className="h-2.5 w-2.5 rounded-full border"
                style={{ backgroundColor: c.bg, borderColor: c.fg }}
                aria-hidden
              />
              {masteryLabels[s]}
            </span>
          );
        })}
      </div>
    </section>
  );
}
