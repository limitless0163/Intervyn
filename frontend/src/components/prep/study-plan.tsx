"use client";

import Link from "next/link";
import { Clock, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { buttonClasses } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { StatusChip } from "@/components/prep/status-chip";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import {
  SAMPLE_STUDY_PLAN,
  type StudyModule,
} from "@/features/prep/sample-mastery";

/**
 * The gap → path view: an ordered list of study modules built from the last
 * interview's weak competencies. Locale-aware client component — each
 * module is a card with its competency, mastery chip, "why it's here", and two
 * CTAs ("Start" to study, "Practice in a mock" to loop back into an interview).
 */
export function StudyPlan({
  modules = SAMPLE_STUDY_PLAN,
  weakAreas,
  sessionId,
  unavailable = false,
}: {
  modules?: StudyModule[];
  /** Weak competencies from the last interview, for the header tie-in. */
  weakAreas?: string[];
  sessionId?: string | null;
  unavailable?: boolean;
}) {
  const messages = useMessages();
  const totalMin = modules.reduce((sum, m) => sum + m.est_min, 0);
  const gaps = weakAreas?.length ? weakAreas : ["your weak areas"];

  return (
    <section
      className="min-w-0 [overflow-wrap:anywhere]"
      aria-labelledby="study-plan-heading"
    >
      <header className="mb-4">
        <Eyebrow>{t(messages, "prep.studyPath")}</Eyebrow>
        <h2
          id="study-plan-heading"
          className="mt-2 font-sans font-semibold tracking-tight text-2xl text-ink"
        >
          {t(messages, "prep.studyPlan")}
        </h2>
        <p className="mt-1 text-[14px] leading-relaxed text-muted">
          {t(messages, "prep.studyPlanIntro")}
          {weakAreas?.length ? (
            <>
              {" — "}
              <span className="text-ink-soft">{gaps.join(", ")}</span>
            </>
          ) : null}
          . {modules.length} {t(messages, "prep.modules")} ·{" "}
          {t(messages, "prep.about")} {totalMin} {t(messages, "prep.min")}.
        </p>
      </header>

      {unavailable && (
        <p
          role="status"
          className="mb-4 rounded-md border border-line bg-accent-soft p-3 text-[13px] text-ink-soft"
        >
          {t(messages, "prep.studyPlanFallback")}
        </p>
      )}

      <ol className="space-y-3">
        {modules.map((m, i) => (
          <li key={m.id}>
            <Card>
              <CardContent className="grid grid-cols-[28px_minmax(0,1fr)] items-start gap-x-4 gap-y-3 py-5">
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-[12px] text-accent"
                  aria-hidden
                >
                  {i + 1}
                </span>

                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-sans font-semibold tracking-tight text-[17px] text-ink">
                      {m.title}
                    </h3>
                    <StatusChip state={m.status} />
                  </div>
                  <p className="mt-1 text-[13.5px] leading-relaxed text-muted">
                    {m.rationale}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] font-mono text-faint">
                    <span>{m.competency}</span>
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden />
                      {m.est_min} {t(messages, "prep.min")}
                    </span>
                  </div>
                </div>

                <div className="col-start-2 flex flex-wrap gap-2">
                  <Link
                    href={`/prep?${new URLSearchParams({
                      ...(sessionId ? { session: sessionId } : {}),
                      module: m.competency,
                    })}#coach-chat`}
                    className={buttonClasses({ size: "sm" })}
                    aria-label={`${t(messages, "prep.start")}: ${m.title}`}
                  >
                    {t(messages, "prep.start")}
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                  <Link
                    href={`/setup?focus=${encodeURIComponent(m.competency)}`}
                    className={buttonClasses({ size: "sm", variant: "out" })}
                    aria-label={`${t(messages, "prep.practiceMock")}: ${m.competency}`}
                  >
                    {t(messages, "prep.practiceMock")}
                  </Link>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}
