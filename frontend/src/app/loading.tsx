import { cookies } from "next/headers";
import { getMessages, t } from "@/lib/i18n";
import { Spinner } from "@/components/ui/spinner";

export default async function Loading() {
  const store = await cookies();
  const messages = getMessages(
    store.get("locale")?.value === "zh" ? "zh" : "en",
  );
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto min-h-screen max-w-[920px] px-6 py-12"
    >
      <div className="flex items-center gap-3 text-sm text-muted">
        <Spinner label={t(messages, "common.loading")} />
        <span>{t(messages, "common.loading")}</span>
      </div>
      <div aria-hidden className="mt-10 space-y-4 motion-safe:animate-pulse">
        <div className="h-9 w-2/3 rounded-md bg-line" />
        <div className="h-5 w-1/2 rounded-md bg-line-2" />
        <div className="mt-8 h-64 rounded-card border border-line bg-panel" />
      </div>
    </main>
  );
}
