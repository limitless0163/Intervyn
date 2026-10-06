"use client";

import { ArrowUpRight, Star } from "lucide-react";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function OpenSource() {
  const messages = useMessages();
  return (
    <section id="github" className="landing-section">
      <Container className="landing-container">
        <h2 className="landing-section-title">
          {t(messages, "landing.openSource.title")}
        </h2>
        <div className="landing-oss-content">
          <div className="landing-oss-copy">
            <div className="landing-github-repo">
              <svg
                width="48"
                height="48"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M12 .75a11.25 11.25 0 0 0-3.558 21.923c.563.104.768-.244.768-.542 0-.267-.01-.974-.015-1.912-3.13.68-3.791-1.51-3.791-1.51-.512-1.3-1.25-1.646-1.25-1.646-1.023-.7.077-.686.077-.686 1.13.08 1.724 1.16 1.724 1.16 1.006 1.724 2.638 1.226 3.28.937.102-.729.394-1.226.715-1.508-2.499-.284-5.126-1.25-5.126-5.565 0-1.23.44-2.233 1.16-3.02-.116-.285-.503-1.43.11-2.98 0 0 .945-.303 3.094 1.154a10.783 10.783 0 0 1 5.624 0c2.148-1.457 3.09-1.154 3.09-1.154.617 1.55.23 2.695.114 2.98.722.787 1.158 1.79 1.158 3.02 0 4.326-2.631 5.278-5.138 5.557.404.35.764 1.041.764 2.098 0 1.515-.014 2.737-.014 3.109 0 .3.203.65.774.54A11.25 11.25 0 0 0 12 .75Z" />
              </svg>
              <span>limitless0163 / Intervyn</span>
            </div>
            <p>{t(messages, "landing.openSource.body")}</p>
            <a
              href="https://github.com/limitless0163/Intervyn"
              target="_blank"
              rel="noopener noreferrer"
              className="landing-button landing-github-button"
            >
              <Star size={17} aria-hidden />
              {t(messages, "landing.openSource.star")}
              <ArrowUpRight size={16} aria-hidden />
            </a>
          </div>
          <div className="landing-terminal">
            <div className="landing-terminal-bar">
              <span />
              <span />
              <span />
              <div>{t(messages, "landing.openSource.terminalTitle")}</div>
            </div>
            <div className="landing-terminal-content">
              <p>{t(messages, "landing.openSource.cloneComment")}</p>
              <pre>
                <code>
                  {
                    "git clone https://github.com/limitless0163/Intervyn.git\ncd Intervyn"
                  }
                </code>
              </pre>
              <p>{t(messages, "landing.openSource.pullComment")}</p>
              <pre>
                <code>git pull</code>
              </pre>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
