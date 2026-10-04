"use client";

import { getMessages, type Dictionary } from "@/lib/i18n";
import { useActiveLocale } from "@/components/locale-provider";

/** Resolve the active interface dictionary from the app-wide locale state. */
export function useMessages(): Dictionary {
  return getMessages(useActiveLocale());
}

/** The active interface locale, also used for coach replies. */
export function useLocale() {
  return useActiveLocale();
}
