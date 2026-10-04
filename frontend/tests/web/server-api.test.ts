import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadSession } from "../../src/services/session";
import { requestPrep } from "../../src/services/api";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/env", () => ({
  serverEnv: {
    agentApiUrl: "https://agent.example/",
    internalApiSecret: "test-secret",
  },
}));
const fetchMock = vi.fn<typeof fetch>();
const view = {
  session_id: "session/1",
  status: "complete",
  progress: [],
  prep_warnings: [],
  context: null,
  scorecard: null,
};
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("server session read", () => {
  it("normalizes the base URL and encodes capability IDs", async () => {
    fetchMock.mockResolvedValue(Response.json(view));
    expect(await loadSession(view.session_id)).toEqual(view);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://agent.example/api/session/session%2F1",
      expect.objectContaining({
        cache: "no-store",
        signal: expect.any(AbortSignal),
      }),
    );
  });
  it.each(["missing", "wrong-session", "bad-json", "network", "shape"])(
    "fails closed for %s",
    async (failure) => {
      if (failure === "network")
        fetchMock.mockRejectedValue(new TypeError("offline"));
      else
        fetchMock.mockResolvedValue(
          failure === "missing"
            ? new Response(null, { status: 404 })
            : failure === "bad-json"
              ? new Response("<html>")
              : Response.json(
                  failure === "shape" ? {} : { ...view, session_id: "other" },
                ),
        );
      expect(await loadSession(view.session_id)).toBeNull();
    },
  );
});
describe("server POST", () => {
  const body = {
    cv_url: "CV text",
    jd_text: "JD text",
    company: "",
    language_mode: { primary: "en" as const, mixed: false },
  };
  it("keeps the private credential on the server and bounds requests", async () => {
    fetchMock.mockResolvedValue(Response.json({ session_id: "session-1" }));
    expect(await requestPrep(body)).toEqual({ session_id: "session-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "https://agent.example/api/prep",
      expect.objectContaining({
        headers: {
          "content-type": "application/json",
          "x-internal-secret": "test-secret",
        },
        signal: expect.any(AbortSignal),
        cache: "no-store",
      }),
    );
  });
  it("does not include raw upstream errors in the thrown message", async () => {
    fetchMock.mockResolvedValue(
      new Response("private-service-data", { status: 502 }),
    );
    await expect(requestPrep(body)).rejects.toThrow(
      "Agent request /api/prep failed (502)",
    );
  });
  it("rejects response contract drift", async () => {
    fetchMock.mockResolvedValue(Response.json({ session_id: 42 }));
    await expect(requestPrep(body)).rejects.toThrow();
  });
});
