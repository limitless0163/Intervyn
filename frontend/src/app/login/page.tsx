"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { createBrowserClient } from "@/lib/supabase/client";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Button, buttonClasses } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { AppShell } from "@/components/ui/app-shell";

/**
 * Post-login destination. Resolve the candidate against a sentinel origin and
 * require it to stay there — this rejects absolute URLs, protocol-relative
 * `//host`, and the URL parser's backslash / control-character normalization
 * tricks (`/\evil.com`, `/%09/evil.com`) that prefix checks miss.
 */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/")) return "/setup";
  try {
    const resolved = new URL(raw, "http://internal");
    if (resolved.origin !== "http://internal") return "/setup";
    return resolved.pathname + resolved.search + resolved.hash;
  } catch {
    return "/setup";
  }
}

export default function LoginPage() {
  const router = useRouter();
  const messages = useMessages();
  // createBrowserClient() reads NEXT_PUBLIC_* (inlined) so this is correct
  // client-side: null means Supabase is unconfigured → dev mode.
  const supabase = useMemo(() => createBrowserClient(), []);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) {
        setError(error.message);
        setBusy(false);
        return;
      }
      // Read ?next= at submit time (client event) — avoids useSearchParams,
      // which would force the prerendered page into a blank Suspense shell.
      router.push(
        safeNext(new URLSearchParams(window.location.search).get("next")),
      );
    } catch {
      setError(t(messages, "auth.requestFailed"));
      setBusy(false);
    }
  }

  return (
    <AppShell className="app-auth">
      <Card>
        <CardHeader>
          <h1 className="font-sans font-semibold tracking-tight text-ink">
            {t(messages, "auth.loginTitle")}
          </h1>
          <CardDescription>{t(messages, "auth.loginSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="pb-6">
          {supabase ? (
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div>
                <Label htmlFor="email">{t(messages, "auth.emailLabel")}</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="password">
                  {t(messages, "auth.passwordLabel")}
                </Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <p className="text-[13px] text-ink-soft" role="alert">
                  {error}
                </p>
              )}
              <Button type="submit" size="lg" disabled={busy}>
                {busy && (
                  <Spinner
                    className="text-current"
                    label={t(messages, "common.loading")}
                  />
                )}
                {t(messages, "auth.signIn")}
              </Button>
              <p className="text-[13px] text-muted">
                {t(messages, "auth.noAccount")}{" "}
                <Link href="/signup">{t(messages, "auth.toSignup")}</Link>
              </p>
            </form>
          ) : (
            <DevModeNotice
              notice={t(messages, "auth.devNotice")}
              cta={t(messages, "auth.devContinue")}
            />
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}

function DevModeNotice({ notice, cta }: { notice: string; cta: string }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-[10px] border border-line bg-accent-soft px-3.5 py-3 text-[13px] text-ink-soft">
        {notice}
      </p>
      <Link
        href="/setup"
        className={buttonClasses({ size: "lg", className: "w-full" })}
      >
        {cta}
      </Link>
    </div>
  );
}
