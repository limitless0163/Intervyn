import { AppShell } from "@/components/ui/app-shell";
import Link from "next/link";
import { cookies } from "next/headers";
import { buttonClasses } from "@/components/ui/button";
import { getMessages, t } from "@/lib/i18n";

export default async function NotFound() {
  const store = await cookies();
  const messages = getMessages(
    store.get("locale")?.value === "zh" ? "zh" : "en",
  );
  return (
    <AppShell className="app-status">
      <h1 className="font-sans font-semibold tracking-tight text-3xl text-ink">
        {t(messages, "common.pageNotFound")}
      </h1>
      <p className="text-muted">{t(messages, "common.pageNotFoundHint")}</p>
      <div className="flex flex-wrap gap-3">
        <Link href="/setup" className={buttonClasses()}>
          {t(messages, "auth.devContinue")}
        </Link>
        <Link href="/" className={buttonClasses({ variant: "out" })}>
          {t(messages, "report.backHome")}
        </Link>
      </div>
    </AppShell>
  );
}
