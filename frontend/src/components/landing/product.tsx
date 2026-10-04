"use client";

import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Reveal } from "@/components/ui/reveal";
import { FeatureRow } from "@/components/landing/feature-row";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

const LANGUAGES = [
  { label: "English", active: true },
  { label: "Tiếng Việt" },
  { label: "Español" },
  { label: "हिन्दी" },
  { label: "Bahasa" },
  { label: "Português" },
  { label: "Filipino" },
  { label: "Français" },
  { label: "+ more" },
];

function LanguagesVisual({
  messages,
}: {
  messages: ReturnType<typeof useMessages>;
}) {
  return (
    <div>
      <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.06em] text-faint">
        {t(messages, "landing.product.languages")}
      </div>
      <div className="flex flex-wrap gap-2">
        {LANGUAGES.map((lang) => (
          <span
            key={lang.label}
            className={
              lang.active
                ? "rounded-lg border border-ink px-[11px] py-1.5 text-[13px] font-medium text-ink"
                : "rounded-lg border border-line bg-[#FCFBF9] px-[11px] py-1.5 text-[13px] text-ink-soft"
            }
          >
            {lang.label}
          </span>
        ))}
      </div>
      <div className="mt-[18px] text-[13.5px] text-muted">
        {t(messages, "landing.product.languagesBody")}
      </div>
    </div>
  );
}

function PlanVisual({
  messages,
}: {
  messages: ReturnType<typeof useMessages>;
}) {
  const planRows = [
    {
      label: "Distributed systems",
      tag: t(messages, "landing.product.probe"),
      strong: true,
    },
    {
      label: "Kafka & event streaming",
      tag: t(messages, "landing.product.gap"),
      strong: true,
    },
    {
      label: "System design — payments",
      tag: t(messages, "landing.product.core"),
      strong: false,
    },
    {
      label: "Behavioral — ownership",
      tag: t(messages, "landing.product.core"),
      strong: false,
    },
    {
      label: "SQL window functions",
      tag: t(messages, "landing.product.warmup"),
      strong: false,
    },
  ];
  return (
    <div>
      <div className="mb-2.5 font-mono text-[11px] uppercase tracking-[0.06em] text-faint">
        {t(messages, "landing.product.plan")}
      </div>
      {planRows.map((row) => (
        <div
          key={row.label}
          className="flex justify-between border-b border-dashed border-line-2 py-2.5 text-[13.5px] last:border-b-0"
        >
          <span>{row.label}</span>
          <span className={row.strong ? "font-semibold text-ok" : "text-muted"}>
            {row.tag}
          </span>
        </div>
      ))}
    </div>
  );
}

function LoopVisual({
  messages,
}: {
  messages: ReturnType<typeof useMessages>;
}) {
  const loopSteps = [
    { badge: "1", label: t(messages, "landing.product.loop1") },
    { badge: "2", label: t(messages, "landing.product.loop2") },
    { badge: "3", label: t(messages, "landing.product.loop3") },
    { badge: "4", label: t(messages, "landing.product.loop4") },
    { badge: "↻", label: t(messages, "landing.product.loop5") },
  ];
  return (
    <div className="flex flex-col gap-2.5">
      {loopSteps.map((step) => (
        <div
          key={step.badge}
          className="flex items-center gap-[11px] text-[13.5px] text-ink-soft"
        >
          <span className="grid h-[26px] w-[26px] place-items-center rounded-[7px] border border-line font-mono text-[11px] text-accent">
            {step.badge}
          </span>
          {step.label}
        </div>
      ))}
    </div>
  );
}

export function Product() {
  const messages = useMessages();
  return (
    <section id="product" className="scroll-mt-24 py-[84px] pt-0">
      <Container>
        <Reveal className="mb-12 max-w-[680px]">
          <Eyebrow>{t(messages, "landing.product.eyebrow")}</Eyebrow>
          <h2 className="serif my-3.5 text-[38px]">
            {t(messages, "landing.product.title")}
          </h2>
        </Reveal>

        <FeatureRow
          first
          eyebrow={t(messages, "landing.product.voiceEyebrow")}
          title={t(messages, "landing.product.voiceTitle")}
          body={t(messages, "landing.product.voiceBody")}
          bullets={[
            t(messages, "landing.product.voiceBullet1"),
            t(messages, "landing.product.voiceBullet2"),
            t(messages, "landing.product.voiceBullet3"),
          ]}
          visual={<LanguagesVisual messages={messages} />}
        />

        <FeatureRow
          flip
          eyebrow={t(messages, "landing.product.tailoredEyebrow")}
          title={t(messages, "landing.product.tailoredTitle")}
          body={t(messages, "landing.product.tailoredBody")}
          bullets={[
            t(messages, "landing.product.tailoredBullet1"),
            t(messages, "landing.product.tailoredBullet2"),
            t(messages, "landing.product.tailoredBullet3"),
          ]}
          visual={<PlanVisual messages={messages} />}
        />

        <FeatureRow
          eyebrow={t(messages, "landing.product.loopEyebrow")}
          title={t(messages, "landing.product.loopTitle")}
          body={t(messages, "landing.product.loopBody")}
          bullets={[
            t(messages, "landing.product.loopBullet1"),
            t(messages, "landing.product.loopBullet2"),
            t(messages, "landing.product.loopBullet3"),
          ]}
          visual={<LoopVisual messages={messages} />}
        />
      </Container>
    </section>
  );
}
