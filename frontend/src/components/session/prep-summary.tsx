"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  AlertTriangle,
  ExternalLink,
  RotateCw,
  ArrowRight,
  UserRound,
  BriefcaseBusiness,
  Building2,
  ScanSearch,
  ListChecks,
  type LucideIcon,
} from "lucide-react";
import type {
  CandidateProfile,
  CompanyIntel,
  GapAnalysis,
  InterviewContext,
  JobSpec,
  QuestionPlan,
} from "@intervyn/shared";
import {
  fetchSessionView,
  resetSessionPolling,
  PREP_STEPS,
  type ClientSessionView,
} from "@/types/session";
import { cn } from "@/utils/cn";
import { safeExternalUrl } from "@/utils/safe-url";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import { Eyebrow } from "@/components/ui/eyebrow";
import { AppShell } from "@/components/ui/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const POLL_MS = 1200;

/** Statuses where prep is finished — stop polling. */
function isTerminal(status: ClientSessionView["status"]): boolean {
  return status !== "prep";
}

/** Header badge label per status (exhaustive, incl. client-side terminals). */
const STATUS_MESSAGE: Record<ClientSessionView["status"], string> = {
  prep: "session.preparing",
  ready: "session.ready",
  scoring: "session.scoring",
  rejected: "session.needsInput",
  error: "session.error",
  complete: "session.complete",
  no_answers: "session.complete",
  not_found: "session.notFound",
  stalled: "session.stalled",
};

export function PrepSummary({
  sessionId,
  persona,
}: {
  sessionId: string;
  persona: string | null;
}) {
  const messages = useMessages();
  const router = useRouter();
  const [view, setView] = useState<ClientSessionView | null>(null);
  // A nonce we bump to force a fresh poll cycle (used by the error Retry).
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    resetSessionPolling(sessionId);
    setView(null);

    async function poll() {
      try {
        const next = await fetchSessionView(sessionId, controller.signal);
        if (controller.signal.aborted) return;
        setView(next);
        // Keep polling only while still preparing.
        if (!isTerminal(next.status)) {
          timer = setTimeout(poll, POLL_MS);
        }
      } catch {
        // Effect cleanup cancels the in-flight request when leaving or retrying.
      }
    }

    poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
      resetSessionPolling(sessionId);
    };
  }, [sessionId, retryKey]);

  const onRetry = useCallback(() => {
    // Restart the 404/deadline bookkeeping so the retry gets a fresh window.
    resetSessionPolling(sessionId);
    setView(null);
    setRetryKey((k) => k + 1);
  }, [sessionId]);

  const goSetup = useCallback(() => router.push("/setup"), [router]);
  const goInterview = useCallback(() => {
    const q = persona ? `?persona=${encodeURIComponent(persona)}` : "";
    router.push(`/interview/${encodeURIComponent(sessionId)}${q}`);
  }, [router, sessionId, persona]);

  const status = view?.status ?? "prep";
  const warnings = view?.prep_warnings ?? [];

  return (
    <AppShell
      className="app-session"
      headerContent={
        <Badge variant="outline">{t(messages, STATUS_MESSAGE[status])}</Badge>
      }
    >
      {status === "prep" && (
        <PrepView progress={view?.progress ?? []} warnings={warnings} />
      )}

      {status === "ready" && view?.context && (
        <ReadyView
          context={view.context}
          warnings={warnings}
          onStart={goInterview}
          onBackToSetup={goSetup}
        />
      )}

      {/* Defensive: ready but no context parsed — treat as still preparing. */}
      {status === "ready" && !view?.context && (
        <PrepView progress={view?.progress ?? []} warnings={warnings} />
      )}

      {(status === "scoring" ||
        status === "complete" ||
        status === "no_answers") && (
        <Card className="mx-auto mt-8 max-w-[760px]">
          <CardContent className="flex flex-col items-start gap-4 py-8">
            <h1 className="font-sans font-semibold tracking-tight text-3xl text-ink">
              {t(
                messages,
                status === "scoring"
                  ? "report.reportStateScoring"
                  : "session.complete",
              )}
            </h1>
            <Link
              href={`/report/${encodeURIComponent(sessionId)}`}
              className={buttonClasses()}
            >
              {t(messages, "interview.viewReport")}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </CardContent>
        </Card>
      )}

      {status === "rejected" && (
        <RejectedView warnings={warnings} onBackToSetup={goSetup} />
      )}

      {status === "error" && (
        <ErrorView onRetry={onRetry} onBackToSetup={goSetup} />
      )}

      {/* Polling deadline passed without a terminal status — honest stall. */}
      {status === "stalled" && (
        <ErrorView
          eyebrow={t(messages, "session.takingLongEyebrow")}
          title={t(messages, "session.prepTooLong")}
          description={t(messages, "session.prepTooLongBody")}
          onRetry={onRetry}
          onBackToSetup={goSetup}
        />
      )}

      {/* Repeated 404s — this session genuinely doesn't exist. */}
      {status === "not_found" && (
        <ErrorView
          eyebrow={t(messages, "session.sessionNotFound")}
          title={t(messages, "session.sessionMissing")}
          description={t(messages, "session.sessionMissingBody")}
          onBackToSetup={goSetup}
        />
      )}
    </AppShell>
  );
}

/* ------------------------------------------------------------------ */
/* Preparing — the agents working                                      */
/* ------------------------------------------------------------------ */

/** Notices shown above prep / bento — input-quality warnings from the agents. */
function WarningBanner({ warnings }: { warnings: string[] }) {
  const messages = useMessages();
  if (warnings.length === 0) return null;
  return (
    <div className="mt-6 flex flex-col gap-2">
      {warnings.map((w, i) => (
        <p
          key={i}
          className="flex items-start gap-2 rounded-[10px] border border-line bg-accent-soft px-3.5 py-2.5 text-[13px] leading-relaxed text-ink-soft"
        >
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-accent"
            aria-hidden
          />
          <span>
            {t(messages, "session.headsUp")} {w}
          </span>
        </p>
      ))}
    </div>
  );
}

function PrepView({
  progress,
  warnings,
}: {
  progress: string[];
  warnings: string[];
}) {
  const messages = useMessages();
  const done = new Set(progress);
  const completed = PREP_STEPS.filter((s) => done.has(s.key)).length;
  const total = PREP_STEPS.length;
  // First step that isn't done yet — the one actively running.
  const active = PREP_STEPS.find((s) => !done.has(s.key));

  return (
    <div className="mx-auto mt-8 max-w-[760px]">
      <h1 className="font-sans font-semibold tracking-tight text-3xl text-ink sm:text-4xl">
        {t(messages, "session.prepTitle")}
      </h1>
      <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-muted">
        {t(messages, "session.prepBody")}
      </p>

      <WarningBanner warnings={warnings} />

      {/* Progress bar */}
      <div className="mt-8">
        <div className="flex items-center justify-between text-[12px] text-faint">
          <span className="font-mono uppercase tracking-[0.12em]">
            {completed} {t(messages, "session.progressOf")} {total}
          </span>
          <span>{Math.round((completed / total) * 100)}%</span>
        </div>
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-line">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
            style={{ width: `${(completed / total) * 100}%` }}
          />
        </div>
      </div>

      {/* Checklist */}
      <Card className="mt-6">
        <CardContent className="flex flex-col gap-1 py-4">
          {PREP_STEPS.map((step) => {
            const isDone = done.has(step.key);
            const isActive = !isDone && active?.key === step.key;
            const labelKey =
              step.key === "cv_analysis"
                ? "setup.stepCv"
                : step.key === "jd_analysis"
                  ? "setup.stepJd"
                  : step.key === "company_research"
                    ? "setup.stepCompany"
                    : step.key === "gap_matching"
                      ? "session.matchingFit"
                      : "setup.stepPlan";
            const label = t(messages, labelKey).replace(
              "{company}",
              t(messages, "session.company"),
            );
            return (
              <div
                key={step.key}
                className={cn(
                  "flex items-center gap-3 rounded-[10px] px-3 py-3 transition-colors",
                  isActive && "bg-accent-soft",
                )}
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                  {isDone ? (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ok-soft">
                      <Check className="h-3 w-3 text-ok" aria-hidden />
                    </span>
                  ) : isActive ? (
                    <Spinner className="h-4 w-4 text-accent" label={label} />
                  ) : (
                    <span
                      className="h-2 w-2 rounded-full bg-line"
                      aria-hidden
                    />
                  )}
                </span>
                <span
                  className={cn(
                    "text-[14px]",
                    isDone
                      ? "text-ink-soft"
                      : isActive
                        ? "font-medium text-ink"
                        : "text-faint",
                  )}
                >
                  {label}
                </span>
                {isDone && (
                  <span className="ml-auto text-[11px] font-mono uppercase tracking-[0.1em] text-ok">
                    {t(messages, "session.done")}
                  </span>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Ready — the "what we found" bento                                   */
/* ------------------------------------------------------------------ */

/** A small chip row; trims to `max` with a "+N" overflow chip. */
function Chips({
  items,
  max = 12,
  variant = "outline",
}: {
  items: string[];
  max?: number;
  variant?: "outline" | "default" | "ok" | "accent";
}) {
  const shown = items.slice(0, max);
  const extra = items.length - shown.length;
  if (items.length === 0) {
    return <span className="text-[13px] text-faint">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((it, i) => (
        <Badge key={`${it}-${i}`} variant={variant} className="font-sans">
          {it}
        </Badge>
      ))}
      {extra > 0 && (
        <Badge variant="outline" className="font-sans text-faint">
          +{extra}
        </Badge>
      )}
    </div>
  );
}

function BentoCard({
  eyebrow,
  title,
  icon: Icon,
  className,
  children,
}: {
  eyebrow: string;
  title: string;
  icon: LucideIcon;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className={cn("flex min-w-0 flex-col overflow-hidden", className)}>
      <CardHeader className="gap-4 pb-5">
        <div className="flex items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] border border-line bg-accent-soft text-accent">
            <Icon className="size-[17px]" aria-hidden />
          </span>
          <Eyebrow>{eyebrow}</Eyebrow>
        </div>
        <CardTitle className="text-[21px] leading-tight break-words">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 pt-0 pb-6">
        {children}
      </CardContent>
    </Card>
  );
}

function CandidateCard({ c }: { c: CandidateProfile }) {
  const messages = useMessages();
  return (
    <BentoCard
      eyebrow={t(messages, "session.candidate")}
      title={c.name || t(messages, "session.candidateFallback")}
      icon={UserRound}
      className="lg:col-span-5"
    >
      <p className="text-[14px] leading-relaxed text-ink-soft">{c.headline}</p>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
        <Badge variant="default" className="font-sans capitalize">
          {c.seniority}
        </Badge>
        <span>
          {c.years_experience}{" "}
          {t(
            messages,
            c.years_experience === 1 ? "session.year" : "session.years",
          )}{" "}
          {t(messages, "session.experience")}
        </span>
      </div>
      <div className="mt-1">
        <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
          {t(messages, "session.topSkills")}
        </p>
        <Chips items={c.skills} max={10} />
      </div>
    </BentoCard>
  );
}

function RoleCard({ j }: { j: JobSpec }) {
  const messages = useMessages();
  return (
    <BentoCard
      eyebrow={t(messages, "session.role")}
      title={j.title || t(messages, "session.targetRole")}
      icon={BriefcaseBusiness}
      className="lg:col-span-7"
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
            {t(messages, "session.mustHave")}
          </p>
          {j.must_have.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {j.must_have.slice(0, 6).map((m, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-[13px] leading-snug text-ink-soft"
                >
                  <span
                    className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent"
                    aria-hidden
                  />
                  {m}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-[13px] text-faint">—</span>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
            {t(messages, "session.niceToHave")}
          </p>
          {j.nice_to_have.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {j.nice_to_have.slice(0, 6).map((m, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-[13px] leading-snug text-muted"
                >
                  <span
                    className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line"
                    aria-hidden
                  />
                  {m}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-[13px] text-faint">—</span>
          )}
        </div>
      </div>
      {j.tech_stack.length > 0 && (
        <div className="mt-1">
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
            {t(messages, "session.techStack")}
          </p>
          <Chips items={j.tech_stack} max={12} />
        </div>
      )}
    </BentoCard>
  );
}

function CompanyCard({ co }: { co: CompanyIntel }) {
  const messages = useMessages();
  const hasIntel = Boolean(co.summary) || co.citations.length > 0;
  return (
    <BentoCard
      eyebrow={t(messages, "session.companyIntel")}
      title={co.name || t(messages, "session.company")}
      icon={Building2}
      className="lg:col-span-5"
    >
      {hasIntel ? (
        <>
          {co.summary && (
            <p className="text-[14px] leading-relaxed text-ink-soft">
              {co.summary}
            </p>
          )}
          {co.industry && (
            <p className="text-[12px] text-muted">{co.industry}</p>
          )}
          {co.citations.length > 0 && (
            <div className="mt-1">
              <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
                {t(messages, "session.sources")}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {co.citations.slice(0, 6).map((cite, i) => (
                  <a
                    key={i}
                    href={safeExternalUrl(cite.url) ?? undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={cite.snippet ?? cite.title}
                    className="inline-flex max-w-[220px] items-center gap-1 rounded-md border border-line bg-paper px-2 py-1 text-[12px] text-ink-soft no-underline transition-colors hover:border-ink hover:no-underline"
                  >
                    <ExternalLink
                      className="h-3 w-3 shrink-0 text-faint"
                      aria-hidden
                    />
                    <span className="truncate">{cite.title}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="text-[13px] leading-relaxed text-muted">
          {t(messages, "session.companyLimited")}
        </p>
      )}
    </BentoCard>
  );
}

function FitCard({ g }: { g: GapAnalysis }) {
  const messages = useMessages();
  return (
    <BentoCard
      eyebrow={t(messages, "session.fit")}
      title={t(messages, "session.match")}
      icon={ScanSearch}
      className="lg:col-span-7"
    >
      {g.summary && (
        <p className="text-[14px] leading-relaxed text-ink-soft">{g.summary}</p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-ok">
            {t(messages, "session.strengths")}
          </p>
          {g.strengths.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {g.strengths.slice(0, 5).map((s, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-[13px] leading-snug text-ink-soft"
                >
                  <Check
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok"
                    aria-hidden
                  />
                  {s}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-[13px] text-faint">—</span>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-accent">
            {t(messages, "session.gapsToProbe")}
          </p>
          {g.gaps.length > 0 || g.probe_targets.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {[...g.gaps, ...g.probe_targets].slice(0, 5).map((s, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-[13px] leading-snug text-ink-soft"
                >
                  <AlertTriangle
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent"
                    aria-hidden
                  />
                  {s}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-[13px] text-faint">—</span>
          )}
        </div>
      </div>
      {g.matched_skills.length > 0 && (
        <div className="mt-1">
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
            {t(messages, "session.matchedSkills")}
          </p>
          <Chips items={g.matched_skills} max={10} variant="ok" />
        </div>
      )}
    </BentoCard>
  );
}

function PlanCard({ p }: { p: QuestionPlan }) {
  const messages = useMessages();
  // Difficulty spread (1–5-ish). Build buckets without unchecked indexing.
  const counts = new Map<number, number>();
  for (const q of p.questions) {
    counts.set(q.difficulty, (counts.get(q.difficulty) ?? 0) + 1);
  }
  const maxCount = Math.max(1, ...Array.from(counts.values()));
  const levels = Array.from(counts.keys()).sort((a, b) => a - b);

  return (
    <BentoCard
      eyebrow={t(messages, "session.interviewPlan")}
      title={`${p.questions.length} ${t(messages, "session.questions")} · ${p.time_budget_min} ${t(messages, "session.minutesShort")}`}
      icon={ListChecks}
      className="lg:col-span-12"
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
            {t(messages, "session.flow")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {p.sections_order.map((s, i) => (
              <span
                key={`${s}-${i}`}
                className="inline-flex items-center rounded-full border border-line bg-paper px-2.5 py-1 text-[12px] text-ink-soft"
              >
                {t(
                  messages,
                  (
                    {
                      intro: "session.stepPrep",
                      behavioral: "session.stepBehavioral",
                      technical: "session.stepTechnical",
                      coding: "session.stepCoding",
                      wrap: "session.stepWrap",
                    } as Record<string, string>
                  )[s] ?? "session.interviewPlan",
                )}
              </span>
            ))}
          </div>
        </div>
        {levels.length > 0 && (
          <div>
            <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
              {t(messages, "session.difficultySpread")}
            </p>
            <div className="flex items-end gap-2">
              {levels.map((lvl) => {
                const n = counts.get(lvl) ?? 0;
                return (
                  <div key={lvl} className="flex flex-col items-center gap-1">
                    <div className="flex h-12 items-end">
                      <div
                        className="w-6 rounded-t bg-accent-soft"
                        style={{
                          height: `${Math.max(8, (n / maxCount) * 100)}%`,
                        }}
                      >
                        <div className="h-1 w-full rounded-t bg-accent" />
                      </div>
                    </div>
                    <span className="text-[11px] font-mono text-faint">
                      L{lvl}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </BentoCard>
  );
}

function ReadyView({
  context,
  warnings,
  onStart,
  onBackToSetup,
}: {
  context: InterviewContext;
  warnings: string[];
  onStart: () => void;
  onBackToSetup: () => void;
}) {
  const messages = useMessages();
  return (
    <div className="mt-8">
      <h1 className="font-sans font-semibold tracking-tight text-3xl text-ink sm:text-4xl">
        {t(messages, "session.whatFound")}
      </h1>
      <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-muted">
        {t(messages, "session.tailoredIntro")
          .replace(
            "{role}",
            context.job.title || t(messages, "session.roleFallback"),
          )
          .replace(
            "{company}",
            context.job.company_name || t(messages, "session.company"),
          )}
      </p>

      <WarningBanner warnings={warnings} />

      {/* Bento grid */}
      <div className="mt-8 grid gap-5 lg:grid-cols-12">
        <CandidateCard c={context.candidate} />
        <RoleCard j={context.job} />
        <FitCard g={context.gap} />
        <CompanyCard co={context.company} />
        <PlanCard p={context.plan} />
      </div>

      {/* CTA */}
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={onStart}>
          {t(messages, "session.startInterview")}
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Button>
        <Button variant="out" size="lg" onClick={onBackToSetup}>
          {t(messages, "session.backToSetup")}
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Rejected — friendly empty state                                     */
/* ------------------------------------------------------------------ */

function RejectedView({
  warnings,
  onBackToSetup,
}: {
  warnings: string[];
  onBackToSetup: () => void;
}) {
  const messages = useMessages();
  return (
    <div className="mx-auto mt-10 max-w-[560px]">
      <Card>
        <CardHeader>
          <Eyebrow>{t(messages, "session.tryAgain")}</Eyebrow>
          <CardTitle className="font-sans font-semibold tracking-tight text-2xl">
            {t(messages, "session.couldntRead")}
          </CardTitle>
          <CardDescription>
            {t(messages, "session.rejectedDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5 pb-6">
          {warnings.length > 0 && (
            <ul className="flex flex-col gap-2">
              {warnings.map((w, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-[13px] leading-relaxed text-ink-soft"
                >
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                    aria-hidden
                  />
                  {w}
                </li>
              ))}
            </ul>
          )}

          <div className="rounded-[10px] border border-line bg-paper px-4 py-3">
            <p className="mb-1.5 text-[11px] font-mono uppercase tracking-[0.1em] text-faint">
              {t(messages, "session.tips")}
            </p>
            <ul className="flex flex-col gap-1.5 text-[13px] leading-relaxed text-muted">
              <li>· {t(messages, "session.tipJob")}</li>
              <li>· {t(messages, "session.tipCv")}</li>
              <li>· {t(messages, "session.tipCompany")}</li>
            </ul>
          </div>

          <Button size="lg" className="self-start" onClick={onBackToSetup}>
            {t(messages, "session.backToSetup")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Error — generic recoverable failure (also stalled / not-found copy) */
/* ------------------------------------------------------------------ */

function ErrorView({
  eyebrow,
  title,
  description,
  onRetry,
  onBackToSetup,
}: {
  eyebrow?: string;
  title?: string;
  description?: string;
  /** Omit to hide the Retry button (e.g. a session that doesn't exist). */
  onRetry?: () => void;
  onBackToSetup: () => void;
}) {
  const messages = useMessages();
  return (
    <div className="mx-auto mt-10 max-w-[520px]">
      <Card>
        <CardHeader>
          <Eyebrow>{eyebrow ?? t(messages, "session.somethingWrong")}</Eyebrow>
          <CardTitle className="font-sans font-semibold tracking-tight text-2xl">
            {title ?? t(messages, "session.prepErrorTitle")}
          </CardTitle>
          <CardDescription>
            {description ?? t(messages, "session.prepErrorBody")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3 pb-6">
          {onRetry && (
            <Button size="lg" onClick={onRetry}>
              <RotateCw className="h-4 w-4" aria-hidden />
              {t(messages, "session.retry")}
            </Button>
          )}
          <Button variant="out" size="lg" onClick={onBackToSetup}>
            {t(messages, "session.backToSetup")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
