"use client";

import { AppShell } from "@/components/ui/app-shell";
import Link from "next/link";
import { Button, buttonClasses } from "@/components/ui/button";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export default function ErrorPage({ reset }: { reset: () => void }) {
  const messages = useMessages();
  return (
    <AppShell className="app-status">
      <h1 className="font-sans font-semibold tracking-tight text-3xl text-ink">
        {t(messages, "common.error")}
      </h1>
      <p role="alert" className="text-muted">
        {t(messages, "common.pageFailed")}
      </p>
      <div className="flex flex-wrap gap-3">
        <Button onClick={reset}>{t(messages, "report.retry")}</Button>
        <Link href="/" className={buttonClasses({ variant: "out" })}>
          {t(messages, "report.backHome")}
        </Link>
      </div>
    </AppShell>
  );
}
