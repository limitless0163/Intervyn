"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function Faq() {
  const messages = useMessages();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const items = Array.from({ length: 10 }, (_, index) => index + 1).map(
    (number) => ({
      q: t(messages, `landing.faq.q${number}`),
      a: t(messages, `landing.faq.a${number}`),
    }),
  );
  return (
    <section id="faq" className="landing-section">
      <Container className="landing-container">
        <h2 className="landing-faq-title">
          {t(messages, "landing.faq.title")}
        </h2>
        <div className="landing-faq-list">
          {items.map((item, index) => {
            const open = expanded.has(index);
            return (
              <div key={index} className="landing-faq-item" data-open={open}>
                <h3>
                  <button
                    type="button"
                    className="landing-faq-trigger"
                    aria-expanded={open}
                    aria-controls={`landing-faq-answer-${index}`}
                    onClick={() =>
                      setExpanded((previous) => {
                        const next = new Set(previous);
                        if (next.has(index)) next.delete(index);
                        else next.add(index);
                        return next;
                      })
                    }
                  >
                    {item.q}
                    <Plus size={24} aria-hidden />
                  </button>
                </h3>
                <div
                  id={`landing-faq-answer-${index}`}
                  className="landing-faq-answer"
                  aria-hidden={!open}
                  inert={!open}
                >
                  <div>
                    <p>{item.a}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Container>
    </section>
  );
}
