import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchSessionView, resetSessionPolling } from "../../src/types/session";

const fetchMock = vi.fn<typeof fetch>();
const id = "session/with spaces?";
const pending = {
  session_id: id,
  status: "prep",
  progress: ["cv_analysis"],
  prep_warnings: [],
  context: null,
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(0);
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  resetSessionPolling(id);
});

afterEach(() => {
  resetSessionPolling(id);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("client session polling", () => {
  it("does not accept another session's terminal response", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...pending, session_id: "other", status: "complete" }),
    );
    expect((await fetchSessionView(id)).status).toBe("prep");
  });
  it("encodes the id and supplies a bounded, cancellable request", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(Response.json(pending));
    expect(await fetchSessionView(id, controller.signal)).toEqual(pending);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/session/${encodeURIComponent(id)}`,
      expect.objectContaining({
        cache: "no-store",
        signal: expect.any(AbortSignal),
      }),
    );
    const signal = fetchMock.mock.calls[0]?.[1]?.signal;
    controller.abort();
    expect(signal?.aborted).toBe(true);
  });

  it("requires consecutive 404s and grants retries a fresh window", async () => {
    fetchMock.mockImplementation(
      async () => new Response(null, { status: 404 }),
    );
    expect((await fetchSessionView(id)).status).toBe("prep");
    expect((await fetchSessionView(id)).status).toBe("prep");
    fetchMock.mockResolvedValueOnce(Response.json(pending));
    await fetchSessionView(id);
    expect((await fetchSessionView(id)).status).toBe("prep");
    expect((await fetchSessionView(id)).status).toBe("prep");
    expect((await fetchSessionView(id)).status).toBe("not_found");
    resetSessionPolling(id);
    expect((await fetchSessionView(id)).status).toBe("prep");
  });

  it("does not accept a terminal-looking payload from a failed HTTP response", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...pending, status: "complete" }, { status: 503 }),
    );
    expect((await fetchSessionView(id)).status).toBe("prep");
  });

  it.each(["prep", "ready"])(
    "keeps %s without context polling and eventually shows a stall",
    async (status) => {
      fetchMock.mockImplementation(async () =>
        Response.json({ ...pending, status }),
      );
      expect((await fetchSessionView(id)).status).toBe("prep");
      vi.setSystemTime(15 * 60 * 1000 + 1);
      const view = await fetchSessionView(id);
      expect(view.status).toBe("stalled");
      expect(view.progress).toEqual(["cv_analysis"]);
    },
  );

  it("checks the deadline after a slow request completes", async () => {
    fetchMock.mockImplementation(async () => {
      vi.setSystemTime(15 * 60 * 1000 + 1);
      return Response.json(pending);
    });
    expect((await fetchSessionView(id)).status).toBe("stalled");
  });

  it.each(["scoring", "complete", "no_answers", "rejected", "error"])(
    "preserves terminal %s even after the prep deadline",
    async (status) => {
      fetchMock.mockResolvedValueOnce(Response.json(pending));
      await fetchSessionView(id);
      vi.setSystemTime(15 * 60 * 1000 + 1);
      fetchMock.mockResolvedValueOnce(Response.json({ ...pending, status }));
      expect((await fetchSessionView(id)).status).toBe(status);
    },
  );

  it("recovers from timeouts but propagates caller cancellation", async () => {
    fetchMock.mockRejectedValue(new DOMException("Timed out", "TimeoutError"));
    expect((await fetchSessionView(id)).status).toBe("prep");
    const controller = new AbortController();
    controller.abort();
    await expect(fetchSessionView(id, controller.signal)).rejects.toMatchObject(
      { name: "AbortError" },
    );
  });
});
