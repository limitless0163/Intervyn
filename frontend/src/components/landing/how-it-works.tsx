"use client";

import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Reveal } from "@/components/ui/reveal";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function HowItWorks() {
  const messages = useMessages();
  const steps = [
    {
      num: "01 — PREP",
      title: t(messages, "landing.how.step1Title"),
      body: t(messages, "landing.how.step1Body"),
    },
    {
      num: "02 — INTERVIEW",
      title: t(messages, "landing.how.step2Title"),
      body: t(messages, "landing.how.step2Body"),
    },
    {
      num: "03 — IMPROVE",
      title: t(messages, "landing.how.step3Title"),
      body: t(messages, "landing.how.step3Body"),
    },
  ];
  return (
    <section id="how" className="scroll-mt-24 py-[84px]">
      <Container>
        <Reveal className="mb-12 max-w-[680px]">
          <Eyebrow>{t(messages, "landing.how.eyebrow")}</Eyebrow>
          <h2 className="serif my-3.5 text-[38px]">
            {t(messages, "landing.how.title")}
          </h2>
          <p className="text-[17px] text-ink-soft">
            {t(messages, "landing.how.body")}
          </p>
        </Reveal>
        <Reveal>
          <div className="grid overflow-hidden rounded-2xl border border-line bg-panel md:grid-cols-3">
            {steps.map((step) => (
              <div
                key={step.num}
                className="border-b border-line px-7 py-[30px] last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0"
              >
                <div className="mb-[18px] font-mono text-[12px] text-accent">
                  {step.num}
                </div>
                <h3 className="mb-[9px] text-[19px] font-semibold">
                  {step.title}
                </h3>
                <p className="text-[14.5px] text-muted">{step.body}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </Container>
    </section>
  );
}
