"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { BrandMark } from "@/components/ui/brand-mark";
import { LandingLanguageMenu } from "@/components/landing/language-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import { cn } from "@/utils/cn";
import "@/styles/landing.css";
import "@/styles/app.css";

/** Shared product navigation, matching the homepage and setup screen. */
export function AppHeader({ children }: { children?: ReactNode }) {
  const messages = useMessages();
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link href="/" className="landing-brand" aria-label="Intervyn">
          <BrandMark size={20} />
          <span>Intervyn</span>
        </Link>
        <div className="app-header-actions">
          {children}
          <Link
            href="/"
            className="app-back"
            aria-label={t(messages, "setup.backHome")}
          >
            <ArrowLeft size={14} aria-hidden />
            <span>{t(messages, "setup.backHome")}</span>
          </Link>
          <LandingLanguageMenu />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

export function AppShell({
  children,
  headerContent,
  className,
}: {
  children: ReactNode;
  headerContent?: ReactNode;
  className?: string;
}) {
  return (
    <div className="app-page">
      <AppHeader>
        {headerContent && (
          <div className="app-desktop-context">{headerContent}</div>
        )}
      </AppHeader>
      <main
        id="main-content"
        tabIndex={-1}
        className={cn("app-container", className)}
      >
        {headerContent && (
          <div className="app-mobile-context">{headerContent}</div>
        )}
        {children}
      </main>
    </div>
  );
}
