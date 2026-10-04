"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { useMessages, useLocale } from "@/hooks/use-i18n";
import { selectLocale } from "@/components/locale-provider";
import { t, type Locale } from "@/lib/i18n";
import { cn } from "@/utils/cn";

const OPTIONS: { value: Locale; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "zh", label: "中文" },
];

/**
 * Minimal locale switcher. Persists the choice in a `locale` cookie and
 * refreshes server components in the new language. English is the default.
 */
export function LanguageToggle({ className }: { className?: string }) {
  const router = useRouter();
  const locale = useLocale();
  const messages = useMessages();

  const choose = useCallback(
    (next: Locale) => {
      if (next === locale) return;
      selectLocale(next);
      router.refresh();
    },
    [locale, router],
  );

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-[10px] border border-line bg-panel p-0.5",
        className,
      )}
      role="group"
      aria-label={t(messages, "common.languageLabel")}
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === locale;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => choose(opt.value)}
            aria-pressed={active}
            className={cn(
              "rounded-md px-2.5 py-1 font-mono text-[11px] font-medium transition-colors",
              active
                ? "bg-accent-soft text-accent"
                : "text-muted hover:text-ink",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
