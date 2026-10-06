"use client";

/**
 * <TextFallback> — the typed-answer accessibility fallback (WP-2).
 *
 * Not everyone can or wants to speak (noisy room, speech difference, mic issue).
 * This input lets the candidate submit a turn by text. Pure presentational: it
 * owns only its draft and calls `onSend(text)`. The LIVE container publishes the
 * text to the room data channel; in PREVIEW it is disabled with a hint.
 */

import * as React from "react";
import { SendHorizontal } from "lucide-react";
import { cn } from "@/utils/cn";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export interface TextFallbackProps {
  onSend: (text: string) => void | Promise<void>;
  disabled?: boolean;
  className?: string;
}

export function TextFallback({
  onSend,
  disabled = false,
  className,
}: TextFallbackProps) {
  const [value, setValue] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const messages = useMessages();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = value.trim();
    if (!text || disabled || sending) return;
    setSending(true);
    setFailed(false);
    try {
      await onSend(text);
      setValue("");
    } catch {
      setFailed(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void submit(event)}
      className={cn("flex items-center gap-2", className)}
      aria-label={t(messages, "interview.typeAnswerLabel")}
    >
      <label htmlFor="di-text-fallback" className="sr-only">
        {t(messages, "interview.typeAnswer")}
      </label>
      <input
        id="di-text-fallback"
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled || sending}
        placeholder={
          disabled
            ? t(messages, "interview.typePlaceholderOffline")
            : t(messages, "interview.typePlaceholder")
        }
        autoComplete="off"
        className={cn(
          "min-w-0 flex-1 rounded-full border border-line bg-paper/80 px-4 py-2.5",
          "text-[14px] text-ink placeholder:text-faint backdrop-blur-sm",
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:border-ink",
          "disabled:opacity-50",
        )}
      />
      <button
        type="submit"
        disabled={disabled || sending || value.trim().length === 0}
        aria-label={t(messages, "interview.sendAnswer")}
        className={cn(
          "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
          "bg-ink text-paper transition-colors duration-150 hover:bg-ink-soft",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
          "disabled:opacity-40 disabled:pointer-events-none",
        )}
      >
        <SendHorizontal className="h-[18px] w-[18px]" aria-hidden />
      </button>
      {failed && (
        <p role="alert" className="text-[13px] text-accent">
          {t(messages, "interview.sendFailed")}
        </p>
      )}
    </form>
  );
}
