"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { createBrowserClient } from "@/lib/supabase/client";
import { publicEnv } from "@/lib/env";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button, buttonClasses } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Spinner } from "@/components/ui/spinner";
import { LanguageToggle } from "@/components/language-toggle";

export default function SignupPage() {
  const router = useRouter();
  const messages = useMessages();
  const supabase = useMemo(() => createBrowserClient(), []);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmSent, setConfirmSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: `${publicEnv.appUrl}/auth/callback` },
      });
      if (error) {
        setError(error.message);
        setBusy(false);
        return;
      }
      // With email confirmation on there's no session yet — tell the user to
      // confirm. When confirmation is disabled a session exists → go to setup.
      if (data.session) {
        router.push("/setup");
        return;
      }
      setConfirmSent(true);
      setBusy(false);
    } catch {
      setError(t(messages, "auth.requestFailed"));
      setBusy(false);
    }
  }

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto flex min-h-screen max-w-[440px] flex-col justify-center px-6 py-16"
    >
      <div className="mb-3 flex items-center justify-between">
        <Eyebrow>{t(messages, "common.appName")}</Eyebrow>
        <LanguageToggle />
      </div>
      <Card className="mt-3">
        <CardHeader>
          <CardTitle>{t(messages, "auth.signupTitle")}</CardTitle>
          <CardDescription>
            {t(messages, "auth.signupSubtitle")}
          </CardDescription>
        </CardHeader>
        <CardContent className="pb-6">
          {!supabase ? (
            <DevModeNotice
              notice={t(messages, "auth.devNotice")}
              cta={t(messages, "auth.devContinue")}
            />
          ) : confirmSent ? (
            <p className="rounded-[10px] border border-line bg-accent-soft px-3.5 py-3 text-[13px] text-ink-soft">
              {t(messages, "auth.checkEmail")}
            </p>
          ) : (
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
                  autoComplete="new-password"
                  required
                  minLength={6}
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
                    className="text-white"
                    label={t(messages, "common.loading")}
                  />
                )}
                {t(messages, "auth.signUp")}
              </Button>
              <p className="text-[13px] text-muted">
                {t(messages, "auth.haveAccount")}{" "}
                <Link href="/login">{t(messages, "auth.toLogin")}</Link>
              </p>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
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
