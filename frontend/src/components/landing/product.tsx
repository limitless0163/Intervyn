"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, ScanText } from "lucide-react";
import { HeroMock } from "@/components/landing/hero-mock";
import { PreviewFrame } from "@/components/landing/preview-frame";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

const FEATURE_KEYS = ["voice", "tailored", "loop"] as const;
const CYCLE_DURATION = 8000;

function PlanVisual() {
  const messages = useMessages();
  const rows = [
    { label: "Distributed systems", tag: "probe", percent: 88 },
    { label: "Kafka & event streaming", tag: "gap", percent: 52 },
    { label: "System design — payments", tag: "core", percent: 76 },
    { label: "Behavioral — ownership", tag: "core", percent: 82 },
    { label: "SQL window functions", tag: "warmup", percent: 64 },
  ];
  return (
    <PreviewFrame title={t(messages, "landing.product.plan")}>
      <div className="landing-plan-content">
        <div className="landing-plan-inputs">
          <span>
            <FileText aria-hidden />
            CV
          </span>
          <span className="landing-plan-connector">↔</span>
          <span>
            <ScanText aria-hidden />
            JD
          </span>
        </div>
        {rows.map((row) => (
          <div key={row.label} className="landing-plan-row">
            <span>{row.label}</span>
            <span
              className={
                row.tag === "gap" ? "landing-plan-gap" : "landing-plan-tag"
              }
            >
              {t(messages, `landing.product.${row.tag}`)}
            </span>
            <div className="landing-plan-line">
              <span style={{ width: `${row.percent}%` }} />
            </div>
          </div>
        ))}
      </div>
    </PreviewFrame>
  );
}

function LoopVisual() {
  const messages = useMessages();
  return (
    <PreviewFrame title={t(messages, "landing.product.loopEyebrow")}>
      <div className="landing-loop-content">
        <div className="landing-loop-scores">
          {[
            ["mockCommunication", "8.5"],
            ["mockSystemDesign", "7.0"],
            ["mockClarity", "9.0"],
          ].map(([key, value]) => (
            <div key={key}>
              <span>{t(messages, `landing.hero.${key}`)}</span>
              <p>
                {value}
                <small>/10</small>
              </p>
            </div>
          ))}
        </div>
        <div className="landing-loop-steps">
          {[1, 2, 3, 4, 5].map((number) => (
            <div key={number}>
              <span>{number === 5 ? "↻" : number}</span>
              <p>{t(messages, `landing.product.loop${number}`)}</p>
            </div>
          ))}
        </div>
      </div>
    </PreviewFrame>
  );
}

export function Product() {
  const messages = useMessages();
  const [active, setActive] = useState(0);
  const [cycle, setCycle] = useState(0);
  const [visible, setVisible] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [documentHidden, setDocumentHidden] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const remaining = useRef(CYCLE_DURATION);
  const selection = useRef("");
  const paused = !visible || reducedMotion || documentHidden;

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setReducedMotion(motion.matches);
    const syncVisibility = () => setDocumentHidden(document.hidden);
    syncMotion();
    syncVisibility();
    motion.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(!!entry?.isIntersecting),
      { threshold: 0.2 },
    );
    if (root.current) observer.observe(root.current);
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
    };
  }, []);

  useEffect(() => {
    const nextSelection = `${active}-${cycle}`;
    if (selection.current !== nextSelection) {
      selection.current = nextSelection;
      remaining.current = CYCLE_DURATION;
    }
    if (paused) return;
    const started = performance.now();
    const timer = setTimeout(
      () => setActive((previous) => (previous + 1) % FEATURE_KEYS.length),
      remaining.current,
    );
    return () => {
      clearTimeout(timer);
      remaining.current = Math.max(
        0,
        remaining.current - (performance.now() - started),
      );
    };
  }, [active, cycle, paused]);

  return (
    <section id="product" className="landing-section">
      <Container className="landing-container">
        <h2 className="landing-section-title">
          {t(messages, "landing.product.title")}
        </h2>
        <div ref={root} className="landing-features">
          <div className="landing-feature-points">
            {FEATURE_KEYS.map((key, index) => {
              const open = active === index;
              return (
                <div
                  key={key}
                  className="landing-feature-item"
                  data-open={open}
                >
                  <h3>
                    <button
                      type="button"
                      aria-expanded={open}
                      aria-controls={`landing-feature-description-${key}`}
                      onClick={() => {
                        setActive(index);
                        setCycle((previous) => previous + 1);
                      }}
                    >
                      {t(messages, `landing.product.${key}Title`)}
                    </button>
                  </h3>
                  <div
                    id={`landing-feature-description-${key}`}
                    className="landing-feature-description"
                    aria-hidden={!open}
                    inert={!open}
                  >
                    <div>
                      <p>{t(messages, `landing.product.${key}Body`)}</p>
                    </div>
                  </div>
                  {open && (
                    <span
                      key={`${active}-${cycle}`}
                      className="landing-feature-progress"
                      style={{
                        animationPlayState: paused ? "paused" : "running",
                      }}
                      aria-hidden
                    />
                  )}
                </div>
              );
            })}
          </div>
          <div className="landing-feature-visual" key={active}>
            {active === 0 ? (
              <HeroMock />
            ) : active === 1 ? (
              <PlanVisual />
            ) : (
              <LoopVisual />
            )}
          </div>
        </div>
      </Container>
    </section>
  );
}
