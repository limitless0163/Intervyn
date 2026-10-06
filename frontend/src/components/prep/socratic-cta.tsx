"use client";

import Link from "next/link";
import { Mic, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { buttonClasses } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

/** Return to the supported voice mock flow after studying with the coach. */
export function SocraticCta() {
  const messages = useMessages();
  return (
    <Card className="bg-accent-soft text-ink">
      <CardContent className="flex flex-col gap-5 py-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <span
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent/10"
            aria-hidden
          >
            <Mic className="h-5 w-5 text-ink" />
          </span>
          <div>
            <Eyebrow className="text-accent">
              {t(messages, "prep.socraticEyebrow")}
            </Eyebrow>
            <h3 className="mt-1.5 font-sans font-semibold tracking-tight text-xl text-ink">
              {t(messages, "prep.socraticTitle")}
            </h3>
            <p className="mt-1 max-w-xl text-[14px] leading-relaxed text-muted">
              {t(messages, "prep.socraticBody")}
            </p>
          </div>
        </div>

        <Link
          href="/setup"
          className={buttonClasses({
            className: "no-underline md:shrink-0",
          })}
        >
          {t(messages, "prep.socraticStart")}
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </CardContent>
    </Card>
  );
}
