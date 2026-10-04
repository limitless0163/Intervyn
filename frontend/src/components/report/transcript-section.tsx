"use client";

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export interface TranscriptTurn {
  question_id: string;
  question: string;
  /** Candidate's answer transcript, or null if the question was not reached. */
  transcript: string | null;
}

/**
 * Per-question playback list: the question text and the candidate's answer
 * transcript. The "▶" is a visual affordance only — no real audio yet (recorded
 * playback lands later). Server component.
 */
export function TranscriptSection({ turns }: { turns: TranscriptTurn[] }) {
  const messages = useMessages();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t(messages, "report.transcript")}</CardTitle>
        <CardDescription>
          {t(messages, "report.transcriptPlayback")}
        </CardDescription>
      </CardHeader>
      <ol className="divide-y divide-line px-6 pb-6">
        {turns.map((turn, i) => (
          <li key={turn.question_id} className="py-4 first:pt-0">
            <div className="flex items-start gap-3">
              <span
                aria-hidden
                className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line bg-paper text-[11px] text-accent"
                title={t(messages, "report.playbackSoon")}
              >
                ▶
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
                  Q{i + 1}
                </p>
                <p className="mt-0.5 text-[14px] font-medium leading-snug text-ink">
                  {turn.question}
                </p>
                {turn.transcript ? (
                  <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                    {turn.transcript}
                  </p>
                ) : (
                  <p className="mt-2 text-sm italic text-faint">
                    {t(messages, "report.transcriptNotReached")}
                  </p>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
