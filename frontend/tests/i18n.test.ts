import { describe, expect, it } from "vitest";
import { en } from "../src/lib/i18n/messages/en";
import { zh } from "../src/lib/i18n/messages/zh";
import { DEFAULT_LOCALE, getMessages, t } from "../src/lib/i18n";

/** Every string leaf path in `en`, e.g. ["nav.setup", "interview.end", ...]. */
function leafPaths(obj: unknown, prefix = ""): string[] {
  if (typeof obj === "string") return [prefix];
  if (obj && typeof obj === "object") {
    return Object.entries(obj).flatMap(([k, v]) =>
      leafPaths(v, prefix ? `${prefix}.${k}` : k),
    );
  }
  return [];
}

describe("Simplified Chinese UI pack", () => {
  it("resolves `zh` to the real dictionary, not English", () => {
    expect(DEFAULT_LOCALE).toBe("en");
    expect(getMessages("zh")).toBe(zh);
    expect(getMessages("en")).toBe(en);
    // Spot-check: the pack is actually translated.
    expect(t(getMessages("zh"), "setup.start")).toBe("开始面试");
    expect(t(getMessages("zh"), "setup.start")).not.toBe(
      t(getMessages("en"), "setup.start"),
    );
  });

  it("covers every `en` key (parity is also enforced by tsc)", () => {
    const missing = leafPaths(en).filter((p) => t(zh, p) === p);
    expect(missing).toEqual([]);
  });

  it("falls back visibly for unknown keys", () => {
    expect(t(getMessages("zh"), "no.such.key")).toBe("no.such.key");
    expect(t(getMessages("en"), "no.such.key")).toBe("no.such.key");
  });
});
