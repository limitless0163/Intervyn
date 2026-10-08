import Link from "next/link";
import { Suspense } from "react";
import { cookies } from "next/headers";
import { RefreshCw, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonClasses } from "@/components/ui/button";
import { AppShell } from "@/components/ui/app-shell";
import { loadSession } from "@/services/session";
import { SAMPLE_SCORECARD } from "@/features/report/sample-scorecard";
import { StudyPlanLoader } from "@/components/prep/study-plan-loader";
import { Spinner } from "@/components/ui/spinner";
import { GroundedChat } from "@/components/prep/grounded-chat";
import { Flashcards } from "@/components/prep/flashcards";
import { MasteryGraphView } from "@/components/prep/mastery-graph";
import { SocraticCta } from "@/components/prep/socratic-cta";
import { getMessages, t } from "@/lib/i18n";

// Reads server-only config (`isSupabaseConfigured()`) and the per-request user;
// must not be statically prerendered.
export const dynamic = "force-dynamic";

/**
 * Prep Coach (WP-4). The closed-loop study surface: it turns the last
 * interview's `weak_competencies` into an ordered study plan, a grounded RAG
 * chat, a spaced-repetition deck, a mastery graph, and a voice Socratic mode —
 * then loops the learner back into a new mock.
 *
 * Server shell: auth-gates only when Supabase is configured (offline it
 * proceeds), then composes the client islands. The report's "Coach me" CTA
 * links here with `?session=`, so the plan is built from THAT interview's real
 * scorecard; the sample card is ONLY the no-session (or lookup-miss) fallback,
 * and is labeled as a preview.
 */
export default async function PrepPage({
  searchParams,
}: {
  searchParams: Promise<{
    session?: string | string[];
    module?: string | string[];
  }>;
}) {
  // No auth gate — OSS runs without sign-in.
  const params = await searchParams;
  const cookieStore = await cookies();
  const messages = getMessages(
    cookieStore.get("locale")?.value === "zh" ? "zh" : "en",
  );
  const sessionId =
    typeof params.session === "string" && params.session
      ? params.session
      : null;

  // Weak areas come from the linked interview's real scorecard when present;
  // otherwise fall back to the clearly-labeled sample.
  const real = sessionId
    ? ((await loadSession(sessionId))?.scorecard ?? null)
    : null;
  const scorecard = real ?? SAMPLE_SCORECARD;
  const isSample = real === null;

  return (
    <AppShell
      headerContent={
        isSample ? (
          <Badge variant="outline">{t(messages, "prepPage.sampleBadge")}</Badge>
        ) : undefined
      }
    >
      <div className="mt-6">
        <h1 className="font-sans font-semibold tracking-tight text-4xl text-ink">
          {t(messages, "prepPage.title")}
        </h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
          {t(
            messages,
            isSample ? "prepPage.sampleIntro" : "prepPage.realIntro",
          )}
        </p>
      </div>

      {/* Loop-back banner */}
      <section className="mt-6">
        <div className="flex flex-col items-start gap-4 rounded-card border border-line bg-accent-soft px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <RefreshCw
              className="mt-0.5 h-5 w-5 shrink-0 text-accent"
              aria-hidden
            />
            <div>
              <h2 className="font-sans font-semibold tracking-tight text-lg text-ink">
                {t(messages, "prepPage.bannerTitle")}
              </h2>
              <p className="mt-0.5 text-[13.5px] text-muted">
                {t(messages, "prepPage.bannerBody")}
              </p>
            </div>
          </div>
          <Link
            href="/setup"
            className={buttonClasses({ className: "sm:shrink-0" })}
          >
            {t(messages, "prepPage.startMock")}
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </section>

      {/* Study plan + grounded chat side by side on wide screens */}
      <section className="mt-10 grid items-start gap-8 lg:grid-cols-[1.15fr_1fr]">
        <Suspense
          fallback={
            <div className="min-h-[320px] rounded-card border border-line bg-panel p-6">
              <div className="flex items-start gap-3 text-sm text-muted">
                <Spinner label={t(messages, "common.loading")} />
                <p>{t(messages, "prep.studyPlanLoading")}</p>
              </div>
            </div>
          }
        >
          <StudyPlanLoader
            scorecard={scorecard}
            sessionId={sessionId}
            isSample={isSample}
          />
        </Suspense>
        <GroundedChat
          sessionId={sessionId}
          topic={typeof params.module === "string" ? params.module : null}
        />
      </section>

      {/* Flashcards + mastery graph */}
      <section className="mt-12 grid gap-10 lg:grid-cols-2">
        <Flashcards />
        <MasteryGraphView />
      </section>

      {/* Voice Socratic mode */}
      <section className="mt-12">
        <SocraticCta />
      </section>
    </AppShell>
  );
}
