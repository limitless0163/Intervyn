"use client";

import { useState } from "react";
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

  return (
    <div className="min-[861px]:hidden">
      <button
        type="button"
        aria-label={t(
          messages,
          open ? "landing.menuClose" : "landing.menuOpen",
        )}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid h-9 w-9 place-items-center rounded-md border border-line text-ink-soft hover:text-ink"
      >
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>

      {open ? (
        <div className="absolute left-0 right-0 top-[66px] border-b border-line bg-paper/95 backdrop-blur-md">
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
      ) : null}
    </div>
  );
}
