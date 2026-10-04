import { beforeEach, describe, expect, it, vi } from "vitest";
import { requestCoachPlan, requestScore } from "../../src/services/api";
import { scorecard } from "./fixtures";

vi.mock("server-only", () => ({}));
const { serverEnv } = vi.hoisted(() => ({
  serverEnv: {
    agentApiUrl: "https://agent.example/",
    internalApiSecret: "internal-test-secret",
  },
}));
vi.mock("@/lib/env", () => ({ serverEnv }));
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  serverEnv.internalApiSecret = "internal-test-secret";
});

describe("server agent requests", () => {
  const cases = [
    {
      path: "/api/score",
      body: { session_id: "session-1" },
      reply: { session_id: "session-1", scorecard: scorecard() },
      send: () => requestScore({ session_id: "session-1" }),
    },
    {
      path: "/api/coach/plan",
      body: { scorecard: scorecard() },
      reply: { modules: [], total_min: 0, summary: "No weak competencies" },
      send: () => requestCoachPlan(scorecard()),
    },
  ];
  it.each(cases)(
    "forwards a contract-valid $path with the internal secret",
    async ({ path, body, reply, send }) => {
      fetchMock.mockResolvedValue(Response.json(reply));
      expect(await send()).toEqual(reply);
      expect(fetchMock).toHaveBeenCalledWith(
        `https://agent.example${path}`,
        expect.objectContaining({
          method: "POST",
          cache: "no-store",
          body: JSON.stringify(body),
          headers: {
            "content-type": "application/json",
            "x-internal-secret": "internal-test-secret",
          },
          signal: expect.any(AbortSignal),
        }),
      );
    },
  );

  it.each(cases)(
    "rejects upstream errors for $path without leaking their body",
    async ({ send }) => {
      fetchMock.mockResolvedValue(
        new Response("private-provider-error", { status: 503 }),
      );
      const error: unknown = await send().catch((error: unknown) => error);
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).toContain("failed (503)");
      expect((error as Error).message).not.toContain("private-provider-error");
    },
  );

  it.each(cases)("rejects response drift for $path", async ({ send }) => {
    fetchMock.mockResolvedValue(Response.json({ invented_response: true }));
    await expect(send()).rejects.toThrow();
  });

  it("supports the OSS configuration with no internal secret", async () => {
    serverEnv.internalApiSecret = "";
    fetchMock.mockResolvedValue(
      Response.json({ session_id: "session-1", scorecard: scorecard() }),
    );
    await requestScore({ session_id: "session-1" });
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toEqual({
      "content-type": "application/json",
    });
  });
});
