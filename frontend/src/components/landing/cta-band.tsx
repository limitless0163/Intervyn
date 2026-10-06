"use client";

import Link from "next/link";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function CtaBand() {
  const messages = useMessages();
  return (
    <section className="landing-closing">
      <Container className="landing-container landing-closing-content">
        <h2 className="landing-section-title">
          {t(messages, "landing.cta.title")}
        </h2>
        <Link href="/setup" className="landing-closing-button">
          {t(messages, "landing.cta.start")}
        </Link>
      </Container>
    </section>
  );
}
