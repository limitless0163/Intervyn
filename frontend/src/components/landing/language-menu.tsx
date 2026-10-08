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
  const entryFocus = useRef<"first" | "last" | "selected">("selected");
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    const items = root.current?.querySelectorAll<HTMLButtonElement>(
      '[role="menuitemradio"]',
    );
    const selected = root.current?.querySelector<HTMLButtonElement>(
      '[aria-checked="true"]',
    );
    const target =
      entryFocus.current === "selected"
        ? selected
        : entryFocus.current === "last"
          ? items?.[items.length - 1]
          : items?.[0];
    target?.focus();
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
        if (event.key === "Escape" && open) {
          event.preventDefault();
          event.stopPropagation();
          setOpen(false);
          trigger.current?.focus();
        }
        if (
          (event.key === "ArrowDown" || event.key === "ArrowUp") &&
          event.target === trigger.current
        ) {
          event.preventDefault();
          entryFocus.current = event.key === "ArrowUp" ? "last" : "first";
          setOpen(true);
          return;
        }
        if (
          open &&
          ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)
        ) {
          event.preventDefault();
          const items = Array.from(
            root.current?.querySelectorAll<HTMLButtonElement>(
              '[role="menuitemradio"]',
            ) ?? [],
          );
          const index = items.indexOf(event.target as HTMLButtonElement);
          const next =
            event.key === "Home"
              ? 0
              : event.key === "End"
                ? items.length - 1
                : (index +
                    (event.key === "ArrowDown" ? 1 : -1) +
                    items.length) %
                  items.length;
          items[next]?.focus();
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
        onClick={() => {
          entryFocus.current = "selected";
          setOpen(!open);
        }}
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
            tabIndex={-1}
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
