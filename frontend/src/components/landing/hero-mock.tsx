"use client";

import { useEffect, useRef, useState } from "react";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function HeroMock() {
  const messages = useMessages();
  const base = t(messages, "landing.hero.mockAnswer");
  const followup = t(messages, "landing.hero.mockFollowup");
  const outcome = t(messages, "landing.hero.mockOutcome");
  const [said, setSaid] = useState(base);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setSaid(base);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const phrases = [base, `${base} ${followup}`, `${base} ${outcome}`];
    let pi = 0;
    let ci = base.length;
    let dir = 1;
    const tick = () => {
      const full = phrases[pi];
      if (!full) return;
      setSaid(full.slice(0, ci));
      ci += dir;
      if (ci > full.length) {
        dir = -1;
        timer.current = setTimeout(tick, 1600);
        return;
      }
      if (ci < base.length) {
        dir = 1;
        pi = (pi + 1) % phrases.length;
      }
      timer.current = setTimeout(tick, dir > 0 ? 42 : 16);
    };
    timer.current = setTimeout(tick, 1200);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [base, followup, outcome]);

  return (
    <div
      aria-hidden="true"
      className="overflow-hidden rounded-2xl border border-line bg-panel shadow-[0_1px_0_rgba(0,0,0,0.02),0_24px_48px_-28px_rgba(20,20,30,0.22)]"
    >
      <div className="flex items-center gap-2 border-b border-line-2 bg-[#FCFBF9] px-3.5 py-[11px]">
        <span className="h-2.5 w-2.5 rounded-full bg-[#E4E0D7]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#E4E0D7]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#E4E0D7]" />
        <span className="ml-2 rounded-md border border-line-2 bg-[#F4F1EA] px-[9px] py-[3px] font-mono text-[11.5px] text-faint">
          localhost:3000/session/8f2a
        </span>
      </div>
      <div className="grid grid-cols-[90px_minmax(0,1fr)] sm:grid-cols-[150px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3 border-r border-line-2 p-3 sm:p-4">
          <div className="relative aspect-square overflow-hidden rounded-xl bg-[linear-gradient(160deg,#23232A,#3C3A4D)]">
            <div className="absolute inset-0 grid place-items-center font-serif text-3xl text-[#D9D6E8]">
              A
            </div>
          </div>
          <div className="flex items-center gap-[7px] font-mono text-[11.5px] text-muted">
            <span className="anim-rec h-[7px] w-[7px] rounded-full bg-[#DC2626]" />{" "}
            04:12
          </div>
          <div className="self-start break-words rounded-md border border-line px-2 py-[3px] font-mono text-[11px] text-ink-soft">
            EN · Recruiter
          </div>
          <div className="self-start break-words rounded-md border border-line px-2 py-[3px] font-mono text-[11px] text-ink-soft">
            Senior Backend
          </div>
        </div>
        <div className="flex min-h-[268px] min-w-0 flex-col gap-[13px] px-3 py-4 sm:px-[18px]">
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2.5">
            <div className="shrink-0 pt-0.5 font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint sm:w-[74px]">
              {t(messages, "landing.hero.mockInterviewer")}
            </div>
            <div className="text-[13.5px] font-[450] leading-[1.5] text-ink">
              {t(messages, "landing.hero.mockQuestion")}
            </div>
          </div>
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2.5">
            <div className="shrink-0 pt-0.5 font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint sm:w-[74px]">
              {t(messages, "landing.hero.mockYou")}
            </div>
            <div className="text-[13.5px] leading-[1.5] text-ink-soft">
              {said}
              <span className="anim-cursor ml-px inline-block h-3.5 w-[7px] translate-y-[2px] bg-accent" />
            </div>
          </div>
          <div className="mt-auto flex flex-wrap gap-[18px] border-t border-line-2 pt-3">
            {[
              [t(messages, "landing.hero.mockCommunication"), "8.5"],
              [t(messages, "landing.hero.mockSystemDesign"), "7.0"],
              [t(messages, "landing.hero.mockClarity"), "9.0"],
            ].map(([k, v]) => (
              <div key={k} className="flex flex-col gap-[3px]">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-faint">
                  {k}
                </span>
                <span className="font-serif text-[19px] text-ink">
                  {v}
                  <small className="text-xs text-faint">/10</small>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
