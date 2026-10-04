"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Reveal } from "@/components/ui/reveal";
import { buttonClasses } from "@/components/ui/button";
import { HeroMock } from "@/components/landing/hero-mock";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function Hero() {
  const messages = useMessages();
  return (
    <header id="top" className="border-b border-line">
      <Container className="grid grid-cols-[minmax(0,1fr)] items-center gap-11 pt-[84px] pb-16 min-[920px]:grid-cols-[minmax(0,1.04fr)_minmax(0,0.96fr)] min-[920px]:gap-14">
        <div className="min-w-0">
          <Eyebrow>{t(messages, "landing.hero.eyebrow")}</Eyebrow>
          <h1 className="serif mt-[18px] mb-[22px] text-[44px] text-ink min-[920px]:text-[60px]">
            {t(messages, "landing.hero.title")}{" "}
            <em className="italic text-accent">
              {t(messages, "landing.hero.accent")}
            </em>
            <br />
            {t(messages, "landing.hero.continuation")}
          </h1>
          <p className="mb-7 max-w-[520px] text-lg text-ink-soft">
            {t(messages, "landing.hero.body")}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/setup" className={buttonClasses()}>
              {t(messages, "landing.nav.start")}
            </Link>
          </div>
          <div className="mt-[18px] flex flex-wrap gap-3.5 text-[13px] text-faint">
            <span className="flex items-center gap-1.5">
              <Check size={14} className="text-ok" />{" "}
              {t(messages, "landing.hero.noCard")}
            </span>
            <span className="flex items-center gap-1.5">
              <Check size={14} className="text-ok" />{" "}
              {t(messages, "landing.hero.selfHost")}
            </span>
            <span className="flex items-center gap-1.5">
              <Check size={14} className="text-ok" />{" "}
              {t(messages, "landing.hero.license")}
            </span>
          </div>
        </div>

        <Reveal className="min-w-0">
          <HeroMock />
        </Reveal>
      </Container>
    </header>
  );
}
