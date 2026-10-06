"use client";

import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function Hero() {
  const messages = useMessages();
  return (
    <header id="top" className="landing-hero">
      <Container className="landing-container relative text-center">
        <h1 className="landing-hero-title">
          <span className="landing-hero-lead">
            {t(messages, "landing.hero.title")}
          </span>{" "}
          <span className="landing-hero-accent">
            {t(messages, "landing.hero.accent")}
          </span>
        </h1>
        <p className="landing-hero-subtitle">
          {t(messages, "landing.hero.continuation")}
        </p>
        <p className="mx-auto mt-7 max-w-[680px] text-[15px] leading-[1.8] text-muted sm:text-base">
          {t(messages, "landing.hero.body")}
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <Link href="/setup" className="landing-button">
            {t(messages, "landing.nav.start")}
            <ArrowRight size={16} aria-hidden />
          </Link>
        </div>
        <div className="mt-5 flex flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-muted">
          {[
            "landing.hero.noCard",
            "landing.hero.selfHost",
            "landing.hero.license",
          ].map((key) => (
            <span key={key} className="flex items-center gap-1.5">
              <Check size={13} className="text-faint" aria-hidden />
              {t(messages, key)}
            </span>
          ))}
        </div>
      </Container>
    </header>
  );
}
