import Link from "next/link";
import { cookies } from "next/headers";
import { isR2Configured, isSupabaseConfigured } from "@/lib/env";
import { getUser } from "@/lib/supabase/server";
import { ArrowLeft } from "lucide-react";
import { BrandMark } from "@/components/ui/brand-mark";
import { Button } from "@/components/ui/button";
import { LandingLanguageMenu } from "@/components/landing/language-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import { SetupForm } from "@/components/setup/setup-form";
import { getMessages, t } from "@/lib/i18n";
import "@/styles/landing.css";
import "@/styles/setup.css";

// Evaluate at request time: `isR2Configured()` reads server env, which must not
// be baked into a static prerender (a deploy with R2 set would otherwise serve a
// stale `r2Configured=false` and never light the upload path).
export const dynamic = "force-dynamic";

/**
 * Setup is a server component so it can read server-only config
 * (`isR2Configured()` is invisible to the browser) and resolve the current
 * user, then hand both into the client form island as props.
 */
export default async function SetupPage() {
  const cookieStore = await cookies();
  const messages = getMessages(
    cookieStore.get("locale")?.value === "zh" ? "zh" : "en",
  );
  // R2 status must be computed server-side — the client can't see server env.
  const r2Configured = isR2Configured();

  // Soft auth signal: surfaces a sign-out affordance when signed in. Page-level
  // gating lives on /interview; setup itself stays reachable in dev mode.
  const user = isSupabaseConfigured() ? await getUser() : null;

  return (
    <div className="landing-page setup-page">
      <header className="landing-nav setup-nav">
        <div className="landing-nav-inner">
          <Link href="/" className="landing-brand">
            <BrandMark size={20} />
            <span>Intervyn</span>
          </Link>
          <div className="flex items-center gap-3 sm:gap-5">
            <Link
              href="/"
              className="setup-back"
              aria-label={t(messages, "setup.backHome")}
            >
              <ArrowLeft size={14} aria-hidden />
              <span>{t(messages, "setup.backHome")}</span>
            </Link>
            <LandingLanguageMenu />
            <ThemeToggle />
            {user && (
              <form action="/auth/signout" method="post">
                <Button type="submit" variant="ghost" size="sm">
                  {t(messages, "setup.signOut")}
                </Button>
              </form>
            )}
          </div>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className="setup-container">
        <SetupForm r2Configured={r2Configured} />
      </main>
    </div>
  );
}
