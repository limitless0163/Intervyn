"use client";

import { Check, Code2, KeyRound, ShieldCheck } from "lucide-react";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function OpenSource() {
  const messages = useMessages();
  return (
    <section id="oss" className="landing-section">
      <Container className="landing-container">
        <h2 className="landing-section-title">
          {t(messages, "landing.openSource.title")}
        </h2>
        <div className="landing-oss-content">
          <div className="landing-oss-copy">
            <p>{t(messages, "landing.openSource.body")}</p>
            <ul>
              {[
                { icon: Code2, label: t(messages, "landing.hero.license") },
                { icon: KeyRound, label: t(messages, "landing.hero.selfHost") },
                {
                  icon: ShieldCheck,
                  label: t(messages, "landing.openSource.ownData"),
                },
              ].map(({ icon: Icon, label }) => (
                <li key={label}>
                  <Icon size={18} aria-hidden />
                  {label}
                </li>
              ))}
            </ul>
          </div>
          <div className="landing-terminal">
            <div className="landing-terminal-bar">
              <span />
              <span />
              <span />
              <div>intervyn / terminal</div>
            </div>
            <div className="landing-terminal-content">
              <p>{t(messages, "landing.openSource.comment")}</p>
              <code>
                <span>$</span> docker compose up --build
              </code>
              <div className="landing-terminal-status">
                <Check size={15} aria-hidden />
                web <span>localhost:3000</span>
              </div>
              <div className="landing-terminal-status">
                <Check size={15} aria-hidden />
                agent <span>localhost:8000</span>
              </div>
              <div className="landing-terminal-status">
                <Check size={15} aria-hidden />
                knowledge <span>localhost:9621</span>
              </div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
