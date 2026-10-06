"use client";

import { useEffect, useRef, useState } from "react";
import { PreviewFrame } from "@/components/landing/preview-frame";
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
    <PreviewFrame title={t(messages, "landing.hero.mockSession")}>
      <div className="landing-preview-content">
        <div className="landing-preview-sidebar">
          <div className="landing-preview-avatar">A</div>
          <div className="landing-preview-recording">
            <span className="anim-rec" />
            04:12
          </div>
          <div className="landing-preview-tag">EN · Recruiter</div>
          <div className="landing-preview-tag">Senior Backend</div>
        </div>
        <div className="landing-preview-conversation">
          <div className="landing-preview-dialog">
            <span className="landing-preview-role">
              {t(messages, "landing.hero.mockInterviewer")}
            </span>
            <p className="landing-preview-question">
              {t(messages, "landing.hero.mockQuestion")}
            </p>
          </div>
          <div className="landing-preview-dialog">
            <span className="landing-preview-role">
              {t(messages, "landing.hero.mockYou")}
            </span>
            <p>
              {said}
              <span className="landing-preview-cursor anim-cursor" />
            </p>
          </div>
          <div className="landing-preview-scores">
            {[
              [t(messages, "landing.hero.mockCommunication"), "8.5"],
              [t(messages, "landing.hero.mockSystemDesign"), "7.0"],
              [t(messages, "landing.hero.mockClarity"), "9.0"],
            ].map(([label, score]) => (
              <div key={label}>
                <span>{label}</span>
                <p>
                  {score}
                  <small>/10</small>
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </PreviewFrame>
  );
}
