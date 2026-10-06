"use client";

/**
 * <AvatarStage> — the avatar centerpiece (WP-9).
 *
 * Two stacked, always-mounted <video loop muted playsInline> layers (idle +
 * speaking) crossfaded by opacity from the `state` prop. WP-2 wires this by
 * passing `useVoiceAssistant().state` straight through — this component stays
 * fully decoupled from LiveKit and is driven entirely by props.
 *
 * Graceful, asset-free fallback (load-bearing): no real loops exist yet, so the
 * placeholder URLs all 404. Rather than flash a broken <video>, the fallback
 * "stage" renders by DEFAULT and a video layer reveals itself only once its
 * `onLoadedData` fires (and hides again on `onError`). With zero assets the
 * fallback is what you see — a calm, editorial gradient panel with the persona
 * name and a state-aware breathing pulse — so the component looks intentional
 * offline. When real MP4s land in `lib/personas.ts`, the videos take over with
 * no code change.
 */

import * as React from "react";
import { cn } from "@/utils/cn";
import type { Persona } from "@/constants/personas";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export interface AvatarStageProps {
  persona: Persona;
  state: AvatarState;
  className?: string;
}

/** Dark persona surfaces follow the setup picker, with distinct cool accents. */
const FALLBACK_STYLE: Record<
  Persona["id"],
  { gradient: string; glow: string; accent: string }
> = {
  anime: {
    gradient: "linear-gradient(165deg, #2b2842 0%, #181824 65%, #121214 100%)",
    glow: "radial-gradient(120% 90% at 50% 18%, rgba(167,155,220,0.12), transparent 60%)",
    accent: "#c4bded",
  },
  superhero: {
    gradient: "linear-gradient(165deg, #34303b 0%, #1c1922 65%, #121214 100%)",
    glow: "radial-gradient(120% 90% at 50% 18%, rgba(175,149,185,0.12), transparent 60%)",
    accent: "#dec0d8",
  },
  recruiter: {
    gradient: "linear-gradient(165deg, #253445 0%, #171d29 65%, #121214 100%)",
    glow: "radial-gradient(120% 90% at 50% 18%, rgba(148,175,218,0.12), transparent 60%)",
    accent: "#bacce8",
  },
  professor: {
    gradient: "linear-gradient(165deg, #293933 0%, #18231f 65%, #121214 100%)",
    glow: "radial-gradient(120% 90% at 50% 18%, rgba(148,190,172,0.12), transparent 60%)",
    accent: "#c0d9ce",
  },
};

type LayerStatus = "loading" | "ready" | "error";

/**
 * Scoped keyframes for the fallback breathing/pulse. Injected as a plain <style>
 * (not styled-jsx) so it needs no globals.css edit and no extra dep. Both
 * animations freeze under `prefers-reduced-motion` per the a11y requirement.
 */
const STAGE_KEYFRAMES = `
@keyframes di-avatar-breathe {
  0%, 100% { opacity: 0.2; transform: scale(1); }
  50%      { opacity: 0.35;  transform: scale(1.03); }
}
@keyframes di-avatar-speak {
  0%, 100% { opacity: 0.25;  transform: scale(1); }
  50%      { opacity: 0.45; transform: scale(1.08); }
}
.di-avatar-pulse { animation: di-avatar-breathe 4.5s ease-in-out infinite; }
.di-avatar-pulse[data-speaking="true"] { animation: di-avatar-speak 1.6s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) {
  .di-avatar-pulse { animation: none !important; }
}
`;

export function AvatarStage({ persona, state, className }: AvatarStageProps) {
  const messages = useMessages();
  const [idleStatus, setIdleStatus] = React.useState<LayerStatus>("loading");
  const [speakStatus, setSpeakStatus] = React.useState<LayerStatus>("loading");
  const idleRef = React.useRef<HTMLVideoElement>(null);
  const speakRef = React.useRef<HTMLVideoElement>(null);

  const speaking = state === "speaking";
  // Everything that isn't `speaking` (idle / listening / thinking) shows idle.
  const showSpeakingLayer = speaking;

  React.useEffect(() => {
    setIdleStatus("loading");
    setSpeakStatus("loading");
  }, [persona.idle_url, persona.speaking_url]);

  React.useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncPlayback = () => {
      for (const [video, active] of [
        [idleRef.current, !speaking],
        [speakRef.current, speaking],
      ] as const) {
        if (!video) continue;
        if (active && !document.hidden && !motion.matches) {
          void video.play().catch(() => {});
        } else {
          video.pause();
        }
      }
    };
    syncPlayback();
    document.addEventListener("visibilitychange", syncPlayback);
    motion.addEventListener("change", syncPlayback);
    return () => {
      document.removeEventListener("visibilitychange", syncPlayback);
      motion.removeEventListener("change", syncPlayback);
      idleRef.current?.pause();
      speakRef.current?.pause();
    };
  }, [speaking, persona.idle_url, persona.speaking_url]);

  const idleReady = idleStatus === "ready";
  const speakReady = speakStatus === "ready";
  // Fallback owns the stage whenever the layer we'd want to show isn't ready.
  const fallbackVisible = showSpeakingLayer ? !speakReady : !idleReady;

  const look = FALLBACK_STYLE[persona.id];
  const stateLabel = t(
    messages,
    `avatars.state${state[0]?.toUpperCase()}${state.slice(1)}`,
  );

  return (
    <div
      className={cn(
        "relative aspect-[4/5] w-full overflow-hidden rounded-card",
        "border border-line bg-panel select-none",
        className,
      )}
      role="img"
      aria-label={`${persona.name} · ${stateLabel}`}
    >
      <style>{STAGE_KEYFRAMES}</style>

      {/* Fallback stage — rendered by default; video layers cover it once ready. */}
      <div
        aria-hidden="true"
        className={cn(
          "absolute inset-0 transition-opacity duration-300 ease-out",
          fallbackVisible ? "opacity-100" : "opacity-0",
        )}
        style={{ background: look.gradient }}
      >
        {/* Soft accent glow + breathing orb behind the name. */}
        <div className="absolute inset-0" style={{ background: look.glow }} />
        <div
          className="di-avatar-pulse absolute left-1/2 top-[34%] h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full blur-2xl"
          data-speaking={speaking}
          style={{ backgroundColor: look.accent, opacity: 0.25 }}
        />

        {/* Persona identity. Sits above the bottom audio visualizer (h-20 in
            voice-stage), so pad clear of that 5rem band to avoid overlap. */}
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-1 px-5 pb-24 text-center">
          <span className="font-sans font-semibold tracking-tight text-2xl text-ink">
            {persona.name}
          </span>
          <span className="max-w-[26ch] text-xs leading-snug text-muted">
            {persona.style}
          </span>
        </div>
      </div>

      {/* Idle layer — visible for idle/listening/thinking. */}
      <video
        ref={idleRef}
        aria-hidden
        className={cn(
          "absolute inset-0 h-full w-full object-cover",
          "transition-opacity duration-300 ease-out",
          !showSpeakingLayer && idleReady ? "opacity-100" : "opacity-0",
        )}
        src={persona.idle_url}
        poster={persona.poster_url}
        loop
        muted
        playsInline
        preload="metadata"
        onLoadedData={() => setIdleStatus("ready")}
        onError={() => setIdleStatus("error")}
      />

      {/* Speaking layer — visible only for `speaking`. */}
      <video
        ref={speakRef}
        aria-hidden
        className={cn(
          "absolute inset-0 h-full w-full object-cover",
          "transition-opacity duration-300 ease-out",
          showSpeakingLayer && speakReady ? "opacity-100" : "opacity-0",
        )}
        src={persona.speaking_url}
        loop
        muted
        playsInline
        preload="metadata"
        onLoadedData={() => setSpeakStatus("ready")}
        onError={() => setSpeakStatus("error")}
      />

      {/* State pill — small, mono, for at-a-glance clarity. */}
      <div className="absolute left-3 top-3 z-10">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5",
            "bg-paper/85 font-mono text-[10px] tracking-[0.12em] text-ink-soft",
            "border border-line backdrop-blur-sm",
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              speaking ? "bg-accent" : "bg-faint",
            )}
          />
          {stateLabel.toUpperCase()}
        </span>
      </div>
    </div>
  );
}
