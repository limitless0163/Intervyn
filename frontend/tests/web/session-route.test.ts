import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "../../src/app/api/session/[id]/route";

vi.mock("@/lib/env", () => ({
  serverEnv: { agentApiUrl: "https://agent.example" },
}));

const fetchMock = vi.fn<typeof fetch>();
const id = "session/with spaces?";

function poll() {
  return GET(new Request("https://web.example/api/session/test"), {
    params: Promise.resolve({ id }),
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("session polling proxy", () => {
  it.each([
    [200, { session_id: id, status: "ready", context: { cursor: 0 } }],
    [404, { detail: "Unknown session" }],
    [500, { detail: "Agent error" }],
  ])("preserves upstream JSON and status %i", async (status, body) => {
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const response = await poll();
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual(body);
    expect(fetchMock).toHaveBeenCalledWith(
      `https://agent.example/api/session/${encodeURIComponent(id)}`,
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it.each(["network", "timeout", "invalid-json", "null-json"])(
    "returns a usable preparing view on %s failure",
    async (failure) => {
      if (failure === "network" || failure === "timeout") {
        fetchMock.mockRejectedValue(
          failure === "network"
            ? new TypeError("fetch failed")
            : new DOMException("Timed out", "TimeoutError"),
        );
      } else {
        fetchMock.mockResolvedValue(
          new Response(failure === "null-json" ? "null" : "<html>error</html>"),
        );
      }
      const response = await poll();
      expect(response.status).toBe(503);
      expect(await response.json()).toEqual({
        session_id: id,
        status: "prep",
        progress: [],
        prep_warnings: [],
        context: null,
      });
    },
  );
});
