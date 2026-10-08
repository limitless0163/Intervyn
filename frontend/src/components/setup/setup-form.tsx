"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { UploadCloud, FileText, X, ArrowRight, Check } from "lucide-react";
import { LANGUAGES, type Language, type LanguageMode } from "@intervyn/shared";
import { startSession } from "@/app/setup/actions";
import { PERSONAS, DEFAULT_PERSONA_ID } from "@/constants/personas";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import { cn } from "@/utils/cn";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { DeviceCheck } from "@/components/setup/device-check";
import { cvFileError, MIN_CV_CHARS, MIN_JD_CHARS } from "@/lib/cv-upload";
import { CvUploadError, fileToDataUrl, uploadCv } from "@/services/cv";

// A small, friendly subset for the picker; full set still lives in LANGUAGES.
const LANGUAGE_LABELS: Partial<Record<Language, string>> = {
  en: "English",
  vi: "Tiếng Việt",
  es: "Español",
  zh: "中文",
  fr: "Français",
  de: "Deutsch",
  ja: "日本語",
};
const OFFERED: Language[] = (
  ["en", "zh", "ja", "vi", "es", "fr", "de"] as Language[]
).filter((l) => (LANGUAGES as readonly string[]).includes(l));

// One-click sample inputs for fast testing / demos. Each is a matched CV + JD +
// company so the prep pipeline gets a coherent pair. Pure UX sugar — clicking a
// sample just fills the form fields; nothing is submitted.
const SAMPLES = [
  {
    id: "backend",
    label: "Backend Engineer · Stripe",
    company: "Stripe",
    cv: "Jordan Rivera — Senior Backend Engineer. 7 years building high-throughput payment and API platforms. Led a ledger service at 5k req/s; cut p99 latency 40% with async batching; owned idempotency and reconciliation. Skills: Python, Go, PostgreSQL, Kafka, gRPC, Kubernetes, distributed systems.",
    jd: "Senior Backend Engineer to build payment APIs at scale. Own services in Python/Go, design event-driven systems with Kafka, and ensure reliability, idempotency, and low p99 latency on PostgreSQL. Strong distributed-systems background required.",
  },
  {
    id: "frontend",
    label: "Frontend Engineer · Vercel",
    company: "Vercel",
    cv: "Sam Chen — Senior Frontend Engineer. 6 years shipping performant React/Next.js apps. Built a design system used across 30+ surfaces; improved LCP 35% with streaming SSR and image optimization. Skills: TypeScript, React, Next.js, Tailwind, accessibility, Core Web Vitals.",
    jd: "Senior Frontend Engineer to build fast, delightful web experiences with Next.js and React. Own component architecture, Core Web Vitals, accessibility, and design-system work. Deep TypeScript and modern rendering (SSR/streaming) experience expected.",
  },
  {
    id: "ml",
    label: "ML Engineer · OpenAI",
    company: "OpenAI",
    cv: "Priya Nair — Machine Learning Engineer. 5 years in production ML: built feature pipelines and model serving for ranking at scale; owned offline/online evaluation and safe rollback. Skills: Python, PyTorch, Ray, feature stores, evaluation, MLOps, monitoring.",
    jd: "Machine Learning Engineer to build and ship production ML systems: data pipelines, training, evaluation, and low-latency serving. You will own offline/online metrics, monitoring, and safe rollouts. Strong Python + PyTorch and MLOps experience required.",
  },
] as const;

export function SetupForm({ r2Configured }: { r2Configured: boolean }) {
  const router = useRouter();
  const messages = useMessages();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  useEffect(() => () => requestRef.current?.abort(), []);

  const [file, setFile] = useState<File | null>(null);
  const [cvText, setCvText] = useState("");
  const [jdText, setJdText] = useState("");
  const [company, setCompany] = useState("");
  const [primary, setPrimary] = useState<Language>("en");
  const [mixed, setMixed] = useState(false);
  const [personaId, setPersonaId] = useState(DEFAULT_PERSONA_ID);

  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Surface inline field errors once the user has interacted with a field (or
  // attempted submit) — not on first load. The submit button stays disabled
  // while invalid, so blur also exposes errors before a submit attempt.
  const [cvTouched, setCvTouched] = useState(false);
  const [jdTouched, setJdTouched] = useState(false);

  // --- Client-side input validation (friendly; backend is the real guard) ---
  // CV is satisfied by a chosen file (length unknown synchronously) OR pasted
  // text of at least MIN_CV_CHARS. JD must be present + reasonably long.
  // Company is optional.
  const cvLen = cvText.trim().length;
  const jdLen = jdText.trim().length;
  const fileError = file ? cvFileError(file) : null;
  const cvError = !file
    ? cvLen === 0
      ? null
      : cvLen < MIN_CV_CHARS
        ? t(messages, "setup.cvTooShort").replace("{min}", String(MIN_CV_CHARS))
        : null
    : fileError
      ? t(messages, `setup.${fileError}`)
      : null;
  const jdError =
    jdLen === 0
      ? null
      : jdLen < MIN_JD_CHARS
        ? t(messages, "setup.jdTooShort").replace("{min}", String(MIN_JD_CHARS))
        : null;
  const materialsValid =
    Boolean(file || cvLen > 0) && jdLen > 0 && !cvError && !jdError;
  const canSubmit = materialsValid && !submitting;

  // Fill the form with a matched sample (testing / demo). Clears any chosen file
  // so the pasted sample CV text is what gets submitted.
  function loadSample(s: (typeof SAMPLES)[number]) {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setCvText(s.cv);
    setJdText(s.jd);
    setCompany(s.company);
    setCvTouched(false);
    setJdTouched(false);
    setError(null);
  }

  function selectFile(selected: File | null) {
    setFile(selected);
    setCvTouched(true);
    setError(null);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (submitting) return;
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) selectFile(dropped);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (requestRef.current) return;
    setError(null);

    // Client-side validation. CV can be a file OR pasted text; JD required +
    // min length; company is optional. Surface inline field errors and bail.
    if (!materialsValid) {
      setCvTouched(true);
      setJdTouched(true);
      return;
    }

    setSubmitting(true);
    const controller = new AbortController();
    requestRef.current = controller;

    try {
      // A selected file takes precedence in both storage and storage-free mode.
      // Pasted text remains available after removing the file.
      let cv_url: string;
      if (file) {
        cv_url = r2Configured
          ? await uploadCv(file, controller.signal)
          : await fileToDataUrl(file, controller.signal);
      } else {
        cv_url = cvText.trim();
      }
      if (controller.signal.aborted) return;

      const language_mode: LanguageMode = {
        primary,
        mixed: primary !== "en" && mixed,
      };
      const result = await startSession({
        cv_url,
        jd_text: jdText.trim(),
        company: company.trim(),
        language_mode,
      });
      if (controller.signal.aborted) return;

      if (!result.ok) {
        // Required-auth distribution and the session expired mid-form →
        // sign back in, then return to setup.
        if (result.reason === "auth_required") {
          router.push("/login?next=/setup");
          return;
        }
        setError(
          t(
            messages,
            result.reason === "invalid_input"
              ? "setup.invalidInput"
              : "setup.startFailed",
          ),
        );
        setSubmitting(false);
        return;
      }

      // Carry the chosen persona forward (PrepRequest has no persona field yet;
      // WP-2 will persist it server-side). Query param keeps P1 stateless.
      // Route to the prep screen — it polls the agent, shows the agents
      // working, then the "what we found" bento, then hands off to /interview.
      router.push(
        `/session/${encodeURIComponent(result.session_id)}${
          personaId ? `?persona=${encodeURIComponent(personaId)}` : ""
        }`,
      );
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(
        err instanceof CvUploadError
          ? t(messages, `setup.${err.key}`)
          : t(messages, "setup.startFailed"),
      );
      setSubmitting(false);
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
    }
  }

  return (
    <form onSubmit={onSubmit} className="setup-form" aria-busy={submitting}>
      <div className="setup-intro">
        <h1 className="setup-title">{t(messages, "setup.title")}</h1>
      </div>

      {/* Quick demo: one-click sample CV + JD + company for fast testing */}
      <Card className="setup-card setup-demo">
        <CardContent className="setup-demo-content">
          <p className="setup-demo-title">{t(messages, "setup.quickDemo")}</p>
          <div className="flex flex-wrap gap-2">
            {SAMPLES.map((s) => (
              <button
                key={s.id}
                type="button"
                disabled={submitting}
                onClick={() => loadSample(s)}
                className="setup-sample"
              >
                {s.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="setup-columns">
        <section className="setup-column" aria-labelledby="setup-materials">
          <h2 id="setup-materials" className="setup-section-label">
            <span aria-hidden>01</span> {t(messages, "setup.materials")}
          </h2>
          {/* CV */}
          <Card className="setup-card">
            <CardHeader>
              <CardTitle className="setup-card-title">
                {t(messages, "setup.cvLabel")}
              </CardTitle>
              <CardDescription>{t(messages, "setup.cvHint")}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 pb-6">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  if (submitting) return;
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={cn(
                  "setup-upload relative rounded-[10px] border border-dashed text-center transition-colors",
                  dragging
                    ? "border-accent bg-accent-soft"
                    : "border-line hover:border-ink",
                )}
              >
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => fileInputRef.current?.click()}
                  aria-label={t(messages, "setup.cvDrop")}
                  aria-invalid={cvTouched && Boolean(cvError)}
                  aria-describedby={
                    cvTouched && cvError ? "cv-error" : undefined
                  }
                  className="flex w-full flex-col items-center gap-2 rounded-[10px] px-10 py-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                >
                  {file ? (
                    <span className="flex min-w-0 max-w-full items-center gap-2 text-[14px] text-ink">
                      <FileText
                        className="h-4 w-4 shrink-0 text-accent"
                        aria-hidden
                      />
                      <span className="break-all">{file.name}</span>
                    </span>
                  ) : (
                    <>
                      <UploadCloud className="h-5 w-5 text-muted" aria-hidden />
                      <span className="text-[13px] text-muted">
                        {t(messages, "setup.cvDrop")}
                      </span>
                    </>
                  )}
                </button>
                {file && (
                  <button
                    type="button"
                    disabled={submitting}
                    aria-label={t(messages, "setup.removeFile")}
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = "";
                    }}
                    className="absolute right-2 top-2 grid h-9 w-9 place-items-center rounded-md text-muted hover:text-ink"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  disabled={submitting}
                  accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                  className="hidden"
                  onChange={(e) => selectFile(e.target.files?.[0] ?? null)}
                />
              </div>
              {file && (
                <p className="text-[12px] text-muted">
                  {t(messages, "setup.fileSelectedHint")}
                </p>
              )}

              <div>
                <Label htmlFor="cvText">
                  {t(messages, "setup.cvPasteLabel")}
                </Label>
                <Textarea
                  id="cvText"
                  rows={4}
                  placeholder={t(messages, "setup.cvPasteHint")}
                  value={cvText}
                  readOnly={submitting}
                  onChange={(e) => setCvText(e.target.value)}
                  onBlur={() => setCvTouched(true)}
                  aria-invalid={cvTouched && Boolean(cvError)}
                  aria-describedby={
                    cvTouched && cvError ? "cv-error" : undefined
                  }
                />
              </div>
              {cvTouched && cvError && (
                <p
                  id="cv-error"
                  className="text-[13px] text-accent"
                  role="alert"
                >
                  {cvError}
                </p>
              )}
            </CardContent>
          </Card>

          {/* JD */}
          <Card className="setup-card setup-jd-card">
            <CardHeader>
              <CardTitle className="setup-card-title">
                {t(messages, "setup.jdLabel")}
              </CardTitle>
              <CardDescription>{t(messages, "setup.jdHint")}</CardDescription>
            </CardHeader>
            <CardContent className="setup-jd-content flex flex-col gap-2 pb-6">
              <Textarea
                rows={6}
                value={jdText}
                readOnly={submitting}
                onChange={(e) => setJdText(e.target.value)}
                onBlur={() => setJdTouched(true)}
                aria-label={t(messages, "setup.jdLabel")}
                aria-invalid={jdTouched && Boolean(jdError)}
                aria-describedby={jdTouched && jdError ? "jd-error" : undefined}
              />
              {jdTouched && jdError && (
                <p
                  id="jd-error"
                  className="text-[13px] text-accent"
                  role="alert"
                >
                  {jdError}
                </p>
              )}
            </CardContent>

            {/* Company */}
            <CardHeader className="setup-company-header">
              <CardTitle className="setup-card-title setup-company-title">
                {t(messages, "setup.companyLabel")}
                <span className="setup-company-optional">
                  {t(messages, "setup.companyOptional")}
                </span>
              </CardTitle>
              <CardDescription>
                {t(messages, "setup.companyHint")}
              </CardDescription>
            </CardHeader>
            <CardContent className="pb-6">
              <Input
                value={company}
                readOnly={submitting}
                onChange={(e) => setCompany(e.target.value)}
                placeholder={t(messages, "setup.companyPlaceholder")}
                aria-label={t(messages, "setup.companyLabel")}
              />
            </CardContent>
          </Card>
        </section>
        <section className="setup-column" aria-labelledby="setup-preferences">
          <h2 id="setup-preferences" className="setup-section-label">
            <span aria-hidden>02</span> {t(messages, "setup.preferences")}
          </h2>
          {/* Language mode */}
          <Card className="setup-card">
            <CardHeader>
              <CardTitle className="setup-card-title">
                {t(messages, "setup.languageLabel")}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 pb-6">
              <div className="flex flex-wrap gap-2">
                {OFFERED.map((lang) => (
                  <button
                    key={lang}
                    type="button"
                    disabled={submitting}
                    onClick={() => {
                      setPrimary(lang);
                      if (lang === "en") setMixed(false);
                    }}
                    aria-pressed={primary === lang}
                    className={cn(
                      "rounded-[10px] border px-3.5 py-2 text-[13px] transition-colors",
                      primary === lang
                        ? "border-accent bg-accent-soft text-accent"
                        : "border-line text-ink-soft hover:border-ink",
                    )}
                  >
                    {LANGUAGE_LABELS[lang] ?? lang}
                  </button>
                ))}
              </div>
              <label
                className={cn(
                  "flex items-center gap-2 text-[13px] text-ink-soft",
                  primary === "en" && "cursor-not-allowed opacity-50",
                )}
              >
                <input
                  type="checkbox"
                  checked={mixed}
                  disabled={primary === "en" || submitting}
                  onChange={(e) => setMixed(e.target.checked)}
                  className="h-4 w-4 accent-[var(--color-accent)] disabled:cursor-not-allowed"
                />
                {t(messages, "setup.languageMixed")}
              </label>
            </CardContent>
          </Card>

          {/* Persona */}
          <Card className="setup-card">
            <CardHeader>
              <CardTitle className="setup-card-title">
                {t(messages, "setup.personaLabel")}
              </CardTitle>
              <CardDescription>
                {t(messages, "setup.personaHint")}
              </CardDescription>
            </CardHeader>
            <CardContent className="setup-personas">
              {PERSONAS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  disabled={submitting}
                  onClick={() => setPersonaId(p.id)}
                  aria-pressed={personaId === p.id}
                  className={cn(
                    "setup-persona",
                    personaId === p.id
                      ? "border-accent bg-accent-soft"
                      : "border-line hover:border-ink",
                  )}
                >
                  <div
                    className="setup-persona-poster"
                    data-persona={p.id}
                    aria-hidden
                  >
                    <span>
                      {p.name
                        .split(" ")
                        .map((part) => part[0])
                        .join("")}
                    </span>
                    {/* The catalog can ship without posters; keep a designed fallback. */}
                    <img
                      src={p.poster_url}
                      alt=""
                      ref={(image) => {
                        if (image?.complete && image.naturalWidth > 0) {
                          image.style.opacity = "1";
                        }
                      }}
                      onLoad={(event) => {
                        event.currentTarget.style.opacity = "1";
                      }}
                      onError={(event) => {
                        event.currentTarget.style.opacity = "0";
                      }}
                    />
                    {personaId === p.id && (
                      <span className="setup-persona-check">
                        <Check size={12} />
                      </span>
                    )}
                  </div>
                  <div>
                    <p className="text-[14px] font-medium text-ink">{p.name}</p>
                    <p className="text-[12px] leading-snug text-muted">
                      {t(
                        messages,
                        `setup.persona${p.id === "anime" ? "Anime" : p.id === "superhero" ? "Superhero" : p.id === "recruiter" ? "Recruiter" : "Professor"}`,
                      )}
                    </p>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          {/* Device check */}
          <Card className="setup-card setup-device-card">
            <CardHeader>
              <CardTitle className="setup-card-title">
                {t(messages, "setup.deviceLabel")}
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-6">
              <DeviceCheck />
            </CardContent>
          </Card>
        </section>
      </div>

      {error && (
        <p className="setup-error" role="alert">
          {error}
        </p>
      )}

      <div className="setup-submit-bar">
        <div className="setup-readiness" role="status" aria-live="polite">
          <span
            className={cn("setup-readiness-dot", canSubmit && "is-ready")}
            aria-hidden
          />
          <p>
            {t(
              messages,
              submitting
                ? "common.loading"
                : canSubmit
                  ? "setup.ready"
                  : "setup.completeMaterials",
            )}
          </p>
        </div>
        <Button
          type="submit"
          size="lg"
          className="setup-start landing-button"
          disabled={!canSubmit}
          aria-disabled={!canSubmit}
        >
          {submitting ? (
            <>
              <Spinner
                className="h-4 w-4 text-current"
                label={t(messages, "common.loading")}
              />
              {t(messages, "common.loading")}
            </>
          ) : (
            <>
              {t(messages, "setup.start")}
              <ArrowRight size={16} aria-hidden />
            </>
          )}
        </Button>
      </div>
    </form>
  );
}
