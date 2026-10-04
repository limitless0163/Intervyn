"use client";

/**
 * <TranscriptPanel> — the live-caption panel (WP-2).
 *
 * Pure presentational + an autoscroll effect. It takes an ordered list of turns
 * and renders them as a frosted, scrollable transcript. Voice-UI convention:
 * captions stay visible for the whole call (accessibility + barge-in clarity),
 * so this panel is always mounted next to the avatar.
 *
 * Data source is decoupled: the LIVE container maps `useTranscriptions()` into
 * `Turn[]`; the PREVIEW container passes a short static sample so the screen
 * looks real fully offline. The whole region is an `aria-live="polite"` log so
 * a screen reader announces new turns as they stream in.
 */

import * as React from "react";
import { cn } from "@/utils/cn";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export type TurnRole = "interviewer" | "candidate";

export interface Turn {
  /** Stable id — use the transcription stream id when live. */
  id: string;
  role: TurnRole;
  text: string;
}

export interface TranscriptPanelProps {
  turns: Turn[];
  /** When true, render a subtle "listening…" affordance under the last turn. */
  live?: boolean;
  className?: string;
  /**
   * Optional ref to the scroll region, so the live container can move focus
   * into the conversation when the room connects (issue #52: keyboard and
   * screen-reader users land in the transcript instead of at the top of the
   * page with no announcement of what changed).
   */
  scrollRegionRef?: React.Ref<HTMLDivElement>;
}

export function TranscriptPanel({
  turns,
  live = false,
  className,
  scrollRegionRef,
}: TranscriptPanelProps) {
  const messages = useMessages();
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const followLatest = React.useRef(true);

  // Merge the internal autoscroll ref with the optional outer focus ref so
  // both keep working when the live container passes one in.
  const setRefs = React.useCallback(
    (el: HTMLDivElement | null) => {
      scrollRef.current = el;
      if (typeof scrollRegionRef === "function") {
        scrollRegionRef(el);
      } else if (scrollRegionRef) {
        scrollRegionRef.current = el;
      }
    },
    [scrollRegionRef],
  );

  // Streaming updates repeatedly cancel smooth scrolling, leaving the latest
  // words below the viewport. Follow instantly, unless the user scrolled back.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el || !followLatest.current) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: "auto",
    });
  }, [turns]);

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-card border border-line",
        "bg-paper/70 backdrop-blur-md",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <span className="font-mono text-[10px] tracking-[0.14em] text-faint">
          {t(messages, "interview.transcript").toUpperCase()}
        </span>
        {live && (
          <span className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.12em] text-muted">
            <span
              className="h-1.5 w-1.5 rounded-full bg-accent motion-safe:animate-pulse"
              aria-hidden
            />
            {t(messages, "interview.live").toUpperCase()}
          </span>
        )}
      </div>

      <div
        ref={setRefs}
        onScroll={(event) => {
          const el = event.currentTarget;
          followLatest.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        className={cn(
          "flex-1 space-y-3.5 overflow-y-auto px-4 py-4",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset",
        )}
        aria-label={t(messages, "interview.transcript")}
        role="log"
        aria-live="polite"
        // A scrollable region must be keyboard-focusable (otherwise keyboard
        // users can never scroll the transcript, and the live container can't
        // move focus into the conversation on connect). `role="log"` already
        // implies a polite live region; the explicit attribute states it for
        // assistive tech that doesn't infer implicit semantics.
        tabIndex={0}
      >
        {turns.length === 0 ? (
          <p className="text-[13px] leading-relaxed text-faint">
            {t(messages, "interview.transcriptEmpty")}
          </p>
        ) : (
          turns.map((turn) => (
            <div key={turn.id} className="flex flex-col gap-1">
              <span
                className={cn(
                  "font-mono text-[10px] tracking-[0.1em]",
                  turn.role === "candidate" ? "text-accent" : "text-faint",
                )}
              >
                {(turn.role === "candidate"
                  ? t(messages, "interview.roleYou")
                  : t(messages, "interview.roleInterviewer")
                ).toUpperCase()}
              </span>
              <p
                className={cn(
                  "text-[14px] leading-relaxed",
                  turn.role === "candidate" ? "text-ink" : "text-ink-soft",
                )}
              >
                {turn.text}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
