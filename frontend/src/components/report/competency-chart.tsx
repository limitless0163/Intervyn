"use client";

import dynamic from "next/dynamic";
import type { CompetencyScore } from "@intervyn/shared";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

const Radar = dynamic(
  () => import("./competency-radar").then((module) => module.CompetencyRadar),
  {
    ssr: false,
    loading: () => (
      <div className="h-[300px] rounded-md bg-line-2 motion-safe:animate-pulse" />
    ),
  },
);

/** Load the chart library separately and expose the same values as text. */
export function CompetencyChart({
  competencies,
}: {
  competencies: CompetencyScore[];
}) {
  const messages = useMessages();
  return (
    <div className="min-w-0">
      <div aria-hidden>
        <Radar competencies={competencies} />
      </div>
      <ul className="sr-only" aria-label={t(messages, "report.competencies")}>
        {competencies.map((item, index) => (
          <li key={`${item.competency}-${index}`}>
            {item.competency}: {item.score} / 5
          </li>
        ))}
      </ul>
    </div>
  );
}
