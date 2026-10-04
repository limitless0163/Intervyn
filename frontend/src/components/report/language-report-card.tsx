"use client";

import type { LanguageReport } from "@intervyn/shared";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

function Stat({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string;
  suffix?: string;
}) {
  return (
    <div className="rounded-[10px] border border-line bg-paper px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
        {label}
      </p>
      <p className="mt-1 font-serif text-2xl text-ink">
        {value}
        {suffix && (
          <span className="ml-0.5 text-base text-faint">{suffix}</span>
        )}
      </p>
    </div>
  );
}

/**
 * Language & delivery report: fluency / clarity on the 0-5 scale, raw filler
 * count, plus the qualitative code-switching and pronunciation notes. Server
 * component.
 */
export function LanguageReportCard({ report }: { report: LanguageReport }) {
  const messages = useMessages();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t(messages, "report.languageDelivery")}</CardTitle>
        <CardDescription>{report.summary}</CardDescription>
      </CardHeader>
      <CardContent className="pb-6">
        <div className="grid grid-cols-3 gap-3">
          <Stat
            label={t(messages, "report.fluency")}
            value={report.fluency_score.toFixed(1)}
            suffix="/5"
          />
          <Stat
            label={t(messages, "report.clarity")}
            value={report.clarity_score.toFixed(1)}
            suffix="/5"
          />
          <Stat
            label={t(messages, "report.fillerWords")}
            value={String(report.filler_word_count)}
          />
        </div>

        <dl className="mt-5 space-y-4">
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
              {t(messages, "report.codeSwitching")}
            </dt>
            <dd className="mt-1 text-sm leading-relaxed text-ink-soft">
              {report.code_switching_notes}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
              {t(messages, "report.pronunciation")}
            </dt>
            <dd className="mt-1 text-sm leading-relaxed text-ink-soft">
              {report.pronunciation_notes}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
