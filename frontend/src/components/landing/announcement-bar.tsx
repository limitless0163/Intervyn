"use client";

import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function AnnouncementBar() {
  const messages = useMessages();
  return (
    <div className="border-b border-line bg-panel">
      <Container className="flex h-[38px] items-center justify-center gap-2.5 text-[13px] text-muted">
        <span
          aria-hidden="true"
          className="inline-block h-[5px] w-[5px] rounded-full bg-accent"
        />
        <b className="font-semibold text-ink">
          {t(messages, "landing.announcement")}
        </b>
      </Container>
    </div>
  );
}
