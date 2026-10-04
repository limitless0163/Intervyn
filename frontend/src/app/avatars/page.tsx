import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { Eyebrow } from "@/components/ui/eyebrow";
import { AvatarGallery } from "@/components/avatar/avatar-gallery";
import { LanguageToggle } from "@/components/language-toggle";
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
    <main className="mx-auto max-w-[1080px] px-6 py-12">
      <header className="flex items-center justify-between">
        <Link href="/" className="no-underline">
          <Eyebrow>Intervyn</Eyebrow>
        </Link>
        <LanguageToggle />
      </header>

      <div className="mt-10 flex flex-col gap-3">
        <Eyebrow>{t(messages, "avatars.eyebrow")}</Eyebrow>
        <h1 className="serif text-4xl text-ink sm:text-5xl">
          {t(messages, "avatars.title")}
        </h1>
        <p className="max-w-[60ch] text-base leading-relaxed text-muted">
          {t(messages, "avatars.body")}
        </p>
      </div>

      <div className="mt-12">
        <AvatarGallery />
      </div>
    </main>
  );
}
