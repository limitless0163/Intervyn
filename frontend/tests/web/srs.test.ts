import { describe, expect, it } from "vitest";
import {
  isDue,
  newCard,
  previewInterval,
  schedule,
  type Rating,
} from "../../src/features/prep/srs";

const now = Date.UTC(2026, 9, 5);
const day = 86_400_000;

describe("flashcard review scheduling", () => {
  it("makes new cards due immediately and honors the exact due boundary", () => {
    const card = newCard(now);
    expect(isDue(card, now - 1)).toBe(false);
    expect(isDue(card, now)).toBe(true);
    expect(card.reps).toBe(0);
  });

  it.each([
    ["again", 1],
    ["hard", 1],
    ["good", 3],
    ["easy", 3],
  ] satisfies [Rating, number][])(
    "schedules the first %s review for %i days",
    (rating, days) => {
      const card = newCard(now);
      const next = schedule(card, rating, now);
      expect(next.due).toBe(now + days * day);
      expect(next.reps).toBe(1);
      expect(previewInterval(card, rating, now)).toBe(`${days}d`);
      expect(card).toEqual(newCard(now));
    },
  );

  it("resets a lapse to one day and bounds repeated difficulty penalties", () => {
    let card = { ...newCard(now), interval: 30 };
    for (let i = 0; i < 20; i++) card = schedule(card, "again", now);
    expect(card.interval).toBe(1);
    expect(card.ease).toBe(1.3);
    expect(card.reps).toBe(20);
    expect(card.due).toBe(now + day);
  });

  it("spaces successful reviews further apart from the caller's review time", () => {
    const first = schedule(newCard(now), "good", now);
    const later = schedule(first, "good", now + 5 * day);
    expect(later.interval).toBeGreaterThan(first.interval);
    expect(later.due).toBe(now + (5 + later.interval) * day);
    expect(later.reps).toBe(2);
  });
});
