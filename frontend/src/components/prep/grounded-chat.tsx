"use client";

import { useEffect, useRef, useState } from "react";
import { Send, ExternalLink, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/utils/cn";
import { askCoach, type Citation } from "@/services/coach";
import { useLocale, useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import { safeExternalUrl } from "@/utils/safe-url";

interface ChatTurn {
  id: string;
  role: "user" | "coach";
  text: string;
  citations?: Citation[];
  followUps?: string[];
}

/**
 * Grounded coach chat. The user asks; we call `askCoach` (which proxies to the
 * agent's Study Coach or a mock), then render the answer with citation chips
 * that link out. When a `sessionId` is provided (the prep page passes the linked
 * interview's id via `?session=`), retrieval is scoped to THAT session's
 * knowledge store — the same key the prep pipeline ingested the CV/JD/company
 * intel under — so answers are grounded in the candidate's own materials.
 * The thinking state is deliberately "RAG-delay friendly" — it names the phase
 * (retrieving → grounding) so a multi-second retrieval feels intentional, not
 * stalled.
 */
export function GroundedChat({
  sessionId,
  topic,
}: {
  sessionId?: string | null;
  topic?: string | null;
}) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);
  const [phase, setPhase] = useState<"retrieving" | "grounding">("retrieving");
  const scrollRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<AbortController | null>(null);
  const followLatest = useRef(true);
  const messages = useMessages();
  const suggestions = [
    t(messages, "prep.suggestion1"),
    t(messages, "prep.suggestion2"),
    t(messages, "prep.suggestion3"),
  ];
  // Answer in the user's chosen language, not always English.
  const locale = useLocale();

  useEffect(() => {
    setTurns([]);
    setInput("");
    setLoading(false);
    setFailedQuestion(null);
    followLatest.current = true;
    return () => {
      requestRef.current?.abort();
      requestRef.current = null;
    };
  }, [sessionId]);

  useEffect(() => {
    if (topic) setInput(topic);
  }, [sessionId, topic]);

  // Cycle the thinking label so a slow retrieval reads as progress.
  useEffect(() => {
    if (!loading) return;
    const t = setTimeout(() => setPhase("grounding"), 900);
    return () => clearTimeout(t);
  }, [loading]);

  // Keep the latest turn in view.
  useEffect(() => {
    if (!followLatest.current) return;
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [turns, loading]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;

    const userTurn: ChatTurn = {
      id: `u-${Date.now()}`,
      role: "user",
      text: q,
    };
    setTurns((prev) => [...prev, userTurn]);
    setInput("");
    setLoading(true);
    setFailedQuestion(null);
    setPhase("retrieving");
    followLatest.current = true;

    try {
      const res = await askCoach(
        q,
        locale,
        sessionId ?? "anonymous",
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setTurns((prev) => [
        ...prev,
        {
          id: `c-${Date.now()}`,
          role: "coach",
          text: res.answer,
          citations: res.citations,
          followUps: res.follow_ups,
        },
      ]);
    } catch {
      if (controller.signal.aborted) return;
      setFailedQuestion(q);
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  }

  return (
    <Card
      id="coach-chat"
      className="flex min-w-0 flex-col scroll-mt-24 lg:sticky lg:top-24"
    >
      <div className="flex items-center justify-between border-b border-line px-6 py-4">
        <div>
          <Eyebrow>{t(messages, "prep.coachEyebrow")}</Eyebrow>
          <h3 className="mt-1 font-sans font-semibold tracking-tight text-lg text-ink">
            {t(messages, "prep.askCoach")}
          </h3>
        </div>
        <Sparkles className="h-4 w-4 text-accent" aria-hidden />
      </div>

      <div
        ref={scrollRef}
        onScroll={(event) => {
          const el = event.currentTarget;
          followLatest.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        role="log"
        aria-label={t(messages, "prep.askCoach")}
        tabIndex={0}
        className="flex-1 space-y-4 overflow-y-auto px-6 py-5"
        style={{ minHeight: 280, maxHeight: 460 }}
      >
        {turns.length === 0 && !loading && (
          <div className="text-[14px] leading-relaxed text-muted">
            <p>{t(messages, "prep.askCoachIntro")}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => ask(s)}
                  className="rounded-full border border-line px-3 py-1.5 text-[12.5px] text-ink-soft transition-colors hover:border-ink hover:bg-panel"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <div
            key={turn.id}
            className={cn(
              "flex",
              turn.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            <div
              className={cn(
                "min-w-0 max-w-[88%] break-words rounded-card px-4 py-3 text-[14px] leading-relaxed [overflow-wrap:anywhere]",
                turn.role === "user"
                  ? "border border-accent/20 bg-accent-soft text-ink"
                  : "border border-line bg-paper text-ink-soft",
              )}
            >
              <p className="whitespace-pre-wrap">{turn.text}</p>

              {turn.citations && turn.citations.length > 0 && (
                <div className="mt-3 border-t border-line pt-3">
                  <p className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-faint">
                    {t(messages, "prep.sources")}
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {turn.citations.map((c, i) => (
                      <a
                        key={`${turn.id}-cite-${i}`}
                        href={safeExternalUrl(c.url) ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group inline-flex items-start gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1.5 text-[12.5px] text-ink-soft no-underline transition-colors hover:border-accent hover:text-accent"
                        title={c.snippet ?? undefined}
                      >
                        <ExternalLink
                          className="mt-0.5 h-3 w-3 shrink-0 text-faint group-hover:text-accent"
                          aria-hidden
                        />
                        <span className="min-w-0">
                          <span className="block font-medium">{c.title}</span>
                          {c.snippet && (
                            <span className="mt-0.5 block text-[11.5px] text-muted">
                              {c.snippet}
                            </span>
                          )}
                        </span>
                      </a>
                    ))}
                  </div>
                </div>
              )}
              {turn.followUps && turns.at(-1)?.id === turn.id && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {turn.followUps.map((question, index) => (
                    <button
                      key={`${turn.id}-follow-${index}`}
                      type="button"
                      disabled={loading}
                      onClick={() => void ask(question)}
                      className="rounded-md border border-line px-2.5 py-1.5 text-left text-[12px] text-accent hover:border-accent disabled:opacity-50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-2.5 rounded-card border border-line bg-paper px-4 py-3 text-[13px] text-muted">
              <Spinner label={t(messages, "prep.thinking")} />
              <span>
                {phase === "retrieving"
                  ? t(messages, "prep.retrieving")
                  : t(messages, "prep.grounding")}
              </span>
            </div>
          </div>
        )}
      </div>

      <CardContent className="border-t border-line py-4">
        {failedQuestion && (
          <div
            role="alert"
            className="mb-3 flex flex-wrap items-center gap-2 text-[13px] text-accent"
          >
            <span>{t(messages, "prep.chatFailed")}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void ask(failedQuestion)}
            >
              {t(messages, "report.retry")}
            </Button>
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={8000}
            placeholder={t(messages, "prep.askWeakArea")}
            aria-label={t(messages, "prep.askCoachLabel")}
            disabled={loading}
            className="min-w-0 flex-1 rounded-[10px] border border-line bg-panel px-3.5 py-2.5 text-[14px] text-ink placeholder:text-faint focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-paper disabled:opacity-50"
          />
          <Button
            type="submit"
            size="md"
            disabled={loading || input.trim().length === 0}
            aria-label={t(messages, "prep.sendQuestion")}
          >
            <Send className="h-4 w-4" aria-hidden />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
