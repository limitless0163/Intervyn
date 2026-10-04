import { en, type Messages } from "./messages/en";
import { zh } from "./messages/zh";

/** Keep translated packs structurally aligned while allowing translated text. */
export type Localized<T> = {
  [K in keyof T]: T[K] extends string ? string : Localized<T[K]>;
};

/** Supported interface locales. English is the default; Chinese is optional. */
export type Locale = "en" | "zh";

export const DEFAULT_LOCALE: Locale = "en";

/**
 * What message readers (`t()`, `useMessages()`) actually handle: the exact
 * `en` key structure with widened string values, so every locale pack fits.
 * `en`'s literals stay the parity anchor (`Messages`); packs are checked
 * against it at compile time in their own files.
 */
export type Dictionary = Localized<Messages>;

const dictionaries: Record<Locale, Dictionary> = {
  en,
  zh,
};

/** Resolve the message dictionary for a locale (defaults to English). */
export function getMessages(locale: Locale = DEFAULT_LOCALE): Dictionary {
  return dictionaries[locale] ?? en;
}

/**
 * Read a dot-path key from a messages dictionary, e.g. `t(messages, "nav.setup")`.
 * Returns the key itself if the path is missing (visible-but-safe fallback).
 */
export function t(messages: Dictionary, key: string): string {
  const value = key
    .split(".")
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === "object"
          ? (acc as Record<string, unknown>)[part]
          : undefined,
      messages,
    );
  return typeof value === "string" ? value : key;
}

export { en };
export type { Messages };
