import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Eyebrow } from "@/components/ui/eyebrow";
import { AvatarGallery } from "@/components/avatar/avatar-gallery";
import { AppShell } from "@/components/ui/app-shell";
import { getMessages, t } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Avatar system · Intervyn",
  description:
    "Preview the Intervyn avatar personas and their idle ⇄ speaking states.",
};

/**
 * Offline-viewable proof for WP-9. Server shell (static, no env reads, no
 * server-only imports) wrapping the <AvatarGallery> client island. Renders
 * fully with zero assets via each stage's fallback.
 */
export default async function AvatarsPage() {
  const cookieStore = await cookies();
  const messages = getMessages(
    cookieStore.get("locale")?.value === "zh" ? "zh" : "en",
  );
  return (
    <AppShell>
      <div className="mt-10 flex flex-col gap-3">
        <Eyebrow>{t(messages, "avatars.eyebrow")}</Eyebrow>
        <h1 className="font-sans font-semibold tracking-tight text-4xl text-ink sm:text-5xl">
          {t(messages, "avatars.title")}
        </h1>
        <p className="max-w-[60ch] text-base leading-relaxed text-muted">
          {t(messages, "avatars.body")}
        </p>
      </div>

      <div className="mt-12">
        <AvatarGallery />
      </div>
    </AppShell>
  );
}
