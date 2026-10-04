"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { LanguageToggle } from "@/components/language-toggle";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

interface MobileMenuProps {
  links: { href: string; label: string }[];
  showLanguageToggle?: boolean;
}

export function MobileMenu({
  links,
  showLanguageToggle = false,
}: MobileMenuProps) {
  const [open, setOpen] = useState(false);
  const messages = useMessages();
  const id = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const desktop = window.matchMedia("(min-width: 861px)");
    const closeOnDesktop = () => {
      if (desktop.matches) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    desktop.addEventListener("change", closeOnDesktop);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      desktop.removeEventListener("change", closeOnDesktop);
    };
  }, [open]);

  return (
    <div
      ref={containerRef}
      className="min-[861px]:hidden"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          triggerRef.current?.focus();
        }
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label={t(
          messages,
          open ? "landing.menuClose" : "landing.menuOpen",
        )}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="grid h-11 w-11 place-items-center rounded-md border border-line text-ink-soft hover:text-ink"
      >
        {open ? <X size={18} aria-hidden /> : <Menu size={18} aria-hidden />}
      </button>

      <div
        id={id}
        hidden={!open}
        className="absolute left-0 right-0 top-[66px] border-b border-line bg-paper/95 backdrop-blur-md"
      >
        <div className="mx-auto flex max-w-[1140px] flex-col px-7 py-3">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="py-2.5 text-[15px] text-ink-soft hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
          {showLanguageToggle && (
            <div className="border-t border-line pt-3 pb-2">
              <LanguageToggle />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
