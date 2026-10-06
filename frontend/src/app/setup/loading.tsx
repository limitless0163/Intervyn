import Link from "next/link";
import { cookies } from "next/headers";
import { BrandMark } from "@/components/ui/brand-mark";
import { Spinner } from "@/components/ui/spinner";
import { getMessages, t } from "@/lib/i18n";
import "@/styles/landing.css";
import "@/styles/setup.css";

export default async function SetupLoading() {
  const store = await cookies();
  const messages = getMessages(
    store.get("locale")?.value === "zh" ? "zh" : "en",
  );

  return (
    <div className="landing-page setup-page">
      <header className="landing-nav setup-nav">
        <div className="landing-nav-inner">
          <Link href="/" className="landing-brand">
            <BrandMark size={20} />
            <span>Intervyn</span>
          </Link>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className="setup-container">
        <Spinner label={t(messages, "common.loading")} />
        <div aria-hidden className="mt-6 space-y-6 motion-safe:animate-pulse">
          <div className="h-12 w-2/3 rounded-lg bg-line" />
          <div className="h-5 w-1/2 rounded-md bg-line-2" />
          <div className="h-24 rounded-card border border-line bg-panel" />
          <div className="setup-columns">
            <div className="h-96 rounded-card border border-line bg-panel" />
            <div className="h-96 rounded-card border border-line bg-panel" />
          </div>
        </div>
      </main>
    </div>
  );
}
