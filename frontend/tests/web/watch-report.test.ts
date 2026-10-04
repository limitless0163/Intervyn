import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { watchReport } from "../../src/features/report/watch-report";
import { scorecard, sessionView } from "./fixtures";

const fetchMock = vi.fn<typeof fetch>();
let stop: (() => void) | undefined;
beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  stop?.();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function watch(overrides: Partial<Parameters<typeof watchReport>[1]> = {}) {
  const options = {
    state: "scoring" as const,
    intervalMs: 1_000,
    stopAfterMs: 10_000,
    isVisible: vi.fn(() => true),
    onChange: vi.fn(),
    onStalled: vi.fn(),
    ...overrides,
  };
  stop = watchReport("session-1", options);
  return options;
}

describe("report polling lifecycle", () => {
  it("refreshes once on a real state change and cancels the deadline", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        sessionView({ status: "complete", scorecard: scorecard() }),
      ),
    );
    const options = watch();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(options.onChange).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/session/session-1",
      expect.objectContaining({
        cache: "no-store",
        signal: expect.any(AbortSignal),
      }),
    );
    await vi.advanceTimersByTimeAsync(20_000);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(options.onStalled).not.toHaveBeenCalled();
  });

  it.each([
    "unchanged",
    "wrong-session",
    "http-error",
    "bad-schema",
    "invalid-json",
    "network",
  ])("keeps the current report on %s and retries", async (failure) => {
    const ready = sessionView({ status: "complete", scorecard: scorecard() });
    if (failure === "network")
      fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    else if (failure === "invalid-json")
      fetchMock.mockResolvedValueOnce(new Response("{"));
    else if (failure === "http-error")
      fetchMock.mockResolvedValueOnce(Response.json(ready, { status: 503 }));
    else if (failure === "bad-schema")
      fetchMock.mockResolvedValueOnce(Response.json({ status: "complete" }));
    else if (failure === "wrong-session")
      fetchMock.mockResolvedValueOnce(
        Response.json({ ...ready, session_id: "other" }),
      );
    else
      fetchMock.mockResolvedValueOnce(
        Response.json(sessionView({ status: "scoring" })),
      );
    const options = watch();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(options.onChange).not.toHaveBeenCalled();
    fetchMock.mockResolvedValueOnce(Response.json(ready));
    await vi.advanceTimersByTimeAsync(1_000);
    expect(options.onChange).toHaveBeenCalledOnce();
  });

  it("does not overlap slow requests", async () => {
    let resolve!: (response: Response) => void;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    watch();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(fetchMock).toHaveBeenCalledOnce();
    fetchMock.mockResolvedValue(
      Response.json(sessionView({ status: "scoring" })),
    );
    resolve(Response.json(sessionView({ status: "scoring" })));
    await vi.advanceTimersByTimeAsync(999);
    expect(fetchMock).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("pauses reads in the background and resumes when visible", async () => {
    const isVisible = vi.fn(() => false);
    const options = watch({ isVisible });
    await vi.advanceTimersByTimeAsync(2_000);
    expect(fetchMock).not.toHaveBeenCalled();
    isVisible.mockReturnValue(true);
    fetchMock.mockResolvedValue(
      Response.json(sessionView({ status: "no_answers" })),
    );
    await vi.advanceTimersByTimeAsync(1_000);
    expect(options.onChange).toHaveBeenCalledOnce();
  });

  it.each(["unmount", "deadline"])(
    "cancels in-flight reads on %s without a late refresh",
    async (reason) => {
      let resolve!: (response: Response) => void;
      fetchMock.mockImplementationOnce(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      );
      const options = watch();
      await vi.advanceTimersByTimeAsync(1_000);
      if (reason === "unmount") stop?.();
      else await vi.advanceTimersByTimeAsync(9_000);
      expect(fetchMock.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
      resolve(
        Response.json(
          sessionView({ status: "complete", scorecard: scorecard() }),
        ),
      );
      await vi.advanceTimersByTimeAsync(20_000);
      expect(options.onChange).not.toHaveBeenCalled();
      expect(options.onStalled).toHaveBeenCalledTimes(
        reason === "deadline" ? 1 : 0,
      );
      expect(fetchMock).toHaveBeenCalledOnce();
    },
  );
});
