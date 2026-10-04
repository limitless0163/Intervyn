"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { watchReport } from "@/features/report/watch-report";
import { Button } from "@/components/ui/button";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

/**
 * Bounded JSON polling avoids repeated server renders and overlapping reads.
 * Refresh the server page only when its report state changes.
 */
export function ScoringPoll({
  sessionId,
  state,
  intervalMs = 2500,
  stopAfterMs = 120_000,
  stalledMessage,
}: {
  sessionId: string;
  state: "scoring" | "preparing";
  intervalMs?: number;
  stopAfterMs?: number;
  stalledMessage?: string;
}) {
  const router = useRouter();
  const messages = useMessages();
  const [stalled, setStalled] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    setStalled(false);
    return watchReport(sessionId, {
      state,
      intervalMs,
      stopAfterMs,
      isVisible: () => document.visibilityState !== "hidden",
      onChange: () => router.refresh(),
      onStalled: () => setStalled(true),
    });
  }, [sessionId, state, router, intervalMs, stopAfterMs, retryKey]);

  if (!stalled) return null;
  return (
    <div className="mt-2 flex flex-col items-center gap-3">
      <p role="status" className="max-w-sm text-sm leading-relaxed text-muted">
        {stalledMessage}
      </p>
      <Button
        variant="out"
        size="sm"
        onClick={() => setRetryKey((key) => key + 1)}
      >
        {t(messages, "report.retry")}
      </Button>
    </div>
  );
}
