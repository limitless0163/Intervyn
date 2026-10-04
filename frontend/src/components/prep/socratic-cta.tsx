"use client";

import Link from "next/link";
import { Mic, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

/**
 * Voice Socratic mode entry point. Reuses the live interview voice loop
 * (LiveKit STT→LLM→TTS) but in a teaching posture: the coach asks leading
 * questions instead of grading. Links to the coach room (placeholder target).
 */
export function SocraticCta() {
  const messages = useMessages();
  return (
    <Card className="bg-ink text-white">
      <CardContent className="flex flex-col gap-5 py-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <span
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white/10"
            aria-hidden
          >
            <Mic className="h-5 w-5 text-white" />
          </span>
          <div>
            <Eyebrow className="text-white/60">
              {t(messages, "prep.socraticEyebrow")}
            </Eyebrow>
            <h3 className="mt-1.5 font-serif text-xl text-white">
              {t(messages, "prep.socraticTitle")}
            </h3>
            <p className="mt-1 max-w-xl text-[14px] leading-relaxed text-white/70">
              {t(messages, "prep.socraticBody")}
            </p>
          </div>
        </div>

        <Link
          href="/interview/coach?mode=socratic"
          className="no-underline md:shrink-0"
        >
          <Button
            variant="out"
            className="border-white/30 bg-white/0 text-white hover:border-white hover:bg-white/10"
          >
            {t(messages, "prep.socraticStart")}
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
