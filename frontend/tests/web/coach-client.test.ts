import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { askCoach } from "../../src/services/coach";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

it("passes the session and language through a cancellable coach request", async () => {
  const reply = { answer: "Use STAR.", citations: [], follow_ups: [] };
  const controller = new AbortController();
  fetchMock.mockResolvedValue(Response.json(reply));
  expect(await askCoach("Help", "zh", "session-1", controller.signal)).toEqual(
    reply,
  );
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe("/api/coach/chat");
  expect(JSON.parse(String(init?.body))).toEqual({
    session_id: "session-1",
    query: "Help",
    lang: "zh",
  });
  controller.abort();
  expect(init?.signal?.aborted).toBe(true);
});

it("rejects HTTP errors so the chat can show its failure state", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 503 }));
  await expect(askCoach("Help")).rejects.toThrow("Coach chat failed (503)");
});
