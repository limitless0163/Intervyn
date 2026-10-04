"use client";

import Link from "next/link";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Reveal } from "@/components/ui/reveal";
import { buttonClasses } from "@/components/ui/button";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function CtaBand() {
  const messages = useMessages();
  return (
    <section className="pb-[84px]">
      <Container>
        <Reveal>
          <div className="rounded-[18px] border border-line bg-panel p-[54px] text-center">
            <Eyebrow>{t(messages, "landing.cta.eyebrow")}</Eyebrow>
            <h2 className="serif mt-3 mb-3.5 text-[38px]">
              {t(messages, "landing.cta.title")}
            </h2>
            <p className="mb-[26px] text-[17px] text-ink-soft">
              {t(messages, "landing.cta.body")}
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link href="/setup" className={buttonClasses()}>
                {t(messages, "landing.cta.start")}
              </Link>
            </div>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}
