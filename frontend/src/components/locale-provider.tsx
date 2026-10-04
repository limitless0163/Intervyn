"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Locale } from "@/lib/i18n";

const LocaleContext = createContext<Locale>("en");

function readLocaleCookie(): Locale {
  if (typeof document === "undefined") return "en";
  const value = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("locale="))
    ?.split("=")[1];
  return value === "zh" ? "zh" : "en";
}

export function LocaleProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: ReactNode;
}) {
  const [locale, setLocale] = useState(initialLocale);

  useEffect(() => {
    const syncLocale = () => setLocale(readLocaleCookie());
    window.addEventListener("intervyn:locale-change", syncLocale);
    return () =>
      window.removeEventListener("intervyn:locale-change", syncLocale);
  }, []);

  useEffect(() => setLocale(initialLocale), [initialLocale]);

  return (
    <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>
  );
}

export function useActiveLocale(): Locale {
  return useContext(LocaleContext);
}

export function selectLocale(locale: Locale): void {
  document.cookie = `locale=${locale}; path=/; max-age=31536000; samesite=lax`;
  document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  window.dispatchEvent(new Event("intervyn:locale-change"));
}
