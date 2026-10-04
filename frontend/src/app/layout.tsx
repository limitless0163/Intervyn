import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
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
    "Open-source, voice-first AI mock interviews. Intervyn reads your CV and the job, researches the company, runs an adaptive voice interview, then shows you exactly what to fix. English-first, 10+ languages.",
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
  // Screen readers pick pronunciation from `lang` — resolve it from the same
  // `locale` cookie the LanguageToggle writes (EN default).
  const store = await cookies();
  const lang = store.get("locale")?.value === "vi" ? "vi" : "en";
  return (
    <html
      lang={lang}
      className={`${inter.variable} ${fraunces.variable} ${jetbrains.variable}`}
    >
      <body className="font-sans">
        <noscript>
          <style
            dangerouslySetInnerHTML={{
              __html: ".reveal{opacity:1!important;transform:none!important}",
            }}
          />
        </noscript>
        {children}
      </body>
    </html>
  );
}
