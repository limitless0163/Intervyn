"use client";

import { cn } from "@/utils/cn";
import type { MasteryState } from "@/features/prep/sample-mastery";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

/** Shared mastery states use dark neutral, blue, violet, and green surfaces. */
export const MASTERY_LABEL: Record<MasteryState, string> = {
  unseen: "Not started",
  learning: "Learning",
  shaky: "Shaky",
  mastered: "Mastered",
};

/** Theme colors for the four states, so node + chip stay in sync. */
export const MASTERY_COLORS: Record<
  MasteryState,
  { bg: string; fg: string; border: string }
> = {
  unseen: {
    bg: "var(--color-line-2)",
    fg: "var(--color-muted)",
    border: "var(--color-line)",
  },
  learning: {
    bg: "var(--color-accent-soft)",
    fg: "var(--color-accent)",
    border: "#3c456b",
  },
  shaky: {
    bg: "var(--color-warning-soft)",
    fg: "var(--color-warning)",
    border: "#4a3c64",
  },
  mastered: {
    bg: "var(--color-ok-soft)",
    fg: "var(--color-ok)",
    border: "#2e5142",
  },
};

export function StatusChip({
  state,
  className,
}: {
  state: MasteryState;
  className?: string;
}) {
  const messages = useMessages();
  const c = MASTERY_COLORS[state];
  const label = t(
    messages,
    `prep.${
      state === "unseen"
        ? "notStarted"
        : state === "learning"
          ? "learning"
          : state === "shaky"
            ? "shaky"
            : "mastered"
    }`,
  );
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5",
        "text-[11px] font-mono font-medium",
        className,
      )}
      style={{ backgroundColor: c.bg, color: c.fg, borderColor: c.border }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: c.fg }}
        aria-hidden
      />
      {label}
    </span>
  );
}
