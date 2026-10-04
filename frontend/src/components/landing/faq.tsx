"use client";

import { Plus } from "lucide-react";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Reveal } from "@/components/ui/reveal";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function Faq() {
  const messages = useMessages();
  const items = [
    { q: t(messages, "landing.faq.q1"), a: t(messages, "landing.faq.a1") },
    { q: t(messages, "landing.faq.q2"), a: t(messages, "landing.faq.a2") },
    { q: t(messages, "landing.faq.q3"), a: t(messages, "landing.faq.a3") },
  ];
  return (
    <section id="faq" className="scroll-mt-24 border-t border-line py-[84px]">
      <Container>
        <Reveal className="mb-8 max-w-[680px]">
          <Eyebrow>{t(messages, "landing.faq.eyebrow")}</Eyebrow>
          <h2 className="serif mt-3.5 text-[38px]">
            {t(messages, "landing.faq.title")}
          </h2>
        </Reveal>
        {items.map((item) => (
          <details key={item.q} className="group border-b border-line py-5">
            <summary className="flex cursor-pointer list-none items-center justify-between text-[17px] font-medium [&::-webkit-details-marker]:hidden">
              {item.q}
              <Plus
                size={18}
                className="text-faint transition-transform duration-200 group-open:rotate-45"
              />
            </summary>
            <p className="mt-3 max-w-[760px] text-[15px] text-ink-soft">
              {item.a}
            </p>
          </details>
        ))}
      </Container>
    </section>
  );
}
