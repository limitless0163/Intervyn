"use client";

import { AudioLines, ChartNoAxesCombined, FileText } from "lucide-react";
import { Container } from "@/components/ui/container";
import { Reveal } from "@/components/ui/reveal";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function HowItWorks() {
  const messages = useMessages();
  const steps = [
    {
      num: "01",
      label: "step1Label",
      icon: FileText,
      art: "prep",
      title: "step1Title",
      body: "step1Body",
    },
    {
      num: "02",
      label: "step2Label",
      icon: AudioLines,
      art: "voice",
      title: "step2Title",
      body: "step2Body",
    },
    {
      num: "03",
      label: "step3Label",
      icon: ChartNoAxesCombined,
      art: "feedback",
      title: "step3Title",
      body: "step3Body",
    },
  ];
  return (
    <section id="how" className="landing-section">
      <Container className="landing-container">
        <Reveal className="landing-section-heading">
          <h2 className="landing-section-title">
            {t(messages, "landing.how.title")}
          </h2>
        </Reveal>
        <div className="grid gap-4 md:grid-cols-3">
          {steps.map((step, index) => (
            <Reveal key={step.num} delay={index * 70} className="h-full">
              <article className={`landing-step landing-step-${step.art}`}>
                <div className="landing-step-art" aria-hidden>
                  <step.icon size={34} strokeWidth={1.2} />
                </div>
                <div className="relative px-6 pt-4 pb-7 sm:px-7">
                  <div className="mb-5 flex items-center justify-between">
                    <span className="text-xs text-muted">
                      {t(messages, `landing.how.${step.label}`)}
                    </span>
                    <span className="font-mono text-xs text-faint">
                      {step.num}
                    </span>
                  </div>
                  <h3 className="mb-3 text-xl font-medium tracking-tight">
                    {t(messages, `landing.how.${step.title}`)}
                  </h3>
                  <p className="text-sm leading-[1.85] text-muted">
                    {t(messages, `landing.how.${step.body}`)}
                  </p>
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </Container>
    </section>
  );
}
