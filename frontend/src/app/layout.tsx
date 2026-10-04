import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
import { LocaleProvider } from "@/components/locale-provider";
import { getMessages, t } from "@/lib/i18n";
import "@/styles/globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-fraunces",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata = {
  metadataBase: process.env.NEXT_PUBLIC_SITE_URL
    ? new URL(process.env.NEXT_PUBLIC_SITE_URL)
    : undefined,
  title: {
    default: "Intervyn — Practice the interview out loud",
    template: "%s · Intervyn",
  },
  description:
    "Open-source, voice-first AI mock interviews with an English or Simplified Chinese interface. Intervyn reads your CV and the job, researches the company, then shows you exactly what to improve. Practice interviews in 10+ languages.",
  applicationName: "Intervyn",
  openGraph: {
    title: "Intervyn — Practice the interview out loud",
    description:
      "Open-source, voice-first AI mock interviews — practice out loud, then pass the real one.",
    url: "/",
    siteName: "Intervyn",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Intervyn — Practice the interview out loud",
    description:
      "Open-source, voice-first AI mock interviews — practice out loud, then pass the real one.",
  },
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  // Screen readers pick pronunciation from `lang`; unsupported legacy locale
  // cookies resolve to the English default.
  const store = await cookies();
  const locale = store.get("locale")?.value === "zh" ? "zh" : "en";
  const lang = locale === "zh" ? "zh-CN" : "en";
  return (
    <html
      lang={lang}
      className={`${inter.variable} ${fraunces.variable} ${jetbrains.variable}`}
    >
      <body className="font-sans">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-panel focus:px-4 focus:py-2 focus:shadow-md"
        >
          {t(getMessages(locale), "common.skipToContent")}
        </a>
        <noscript>
          <style
            dangerouslySetInnerHTML={{
              __html: ".reveal{opacity:1!important;transform:none!important}",
            }}
          />
        </noscript>
        <LocaleProvider initialLocale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
