"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, Globe2 } from "lucide-react";
import { selectLocale } from "@/components/locale-provider";
import { useLocale, useMessages } from "@/hooks/use-i18n";
import { t, type Locale } from "@/lib/i18n";

const OPTIONS: { value: Locale; label: string }[] = [
  { value: "en", label: "English" },
  { value: "zh", label: "中文" },
];

export function LandingLanguageMenu() {
  const locale = useLocale();
  const messages = useMessages();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return (
    <div
      ref={root}
      className="landing-language"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          trigger.current?.focus();
        }
        if (event.key === "ArrowDown" && event.target === trigger.current) {
          event.preventDefault();
          setOpen(true);
          requestAnimationFrame(() =>
            root.current
              ?.querySelector<HTMLButtonElement>('[role="menuitemradio"]')
              ?.focus(),
          );
        }
      }}
    >
      <button
        ref={trigger}
        type="button"
        className="landing-language-trigger"
        aria-label={t(messages, "common.languageLabel")}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <Globe2 size={18} aria-hidden />
        <span>{locale === "en" ? "English" : "中文"}</span>
        <ChevronDown size={12} aria-hidden />
      </button>
      <div
        id={id}
        role="menu"
        aria-label={t(messages, "common.languageLabel")}
        hidden={!open}
        className="landing-language-options"
      >
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="menuitemradio"
            aria-checked={locale === option.value}
            onClick={() => {
              selectLocale(option.value);
              setOpen(false);
              trigger.current?.focus();
              router.refresh();
            }}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
