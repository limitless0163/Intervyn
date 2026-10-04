import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoachReplySchema, KbQueryResponseSchema } from "@intervyn/shared";
import { POST as coachPost } from "../../src/app/api/coach/chat/route";
import { POST as kbPost } from "../../src/app/api/kb/query/route";

const { getUser, gateRequest } = vi.hoisted(() => ({
  getUser: vi.fn(),
  gateRequest: vi.fn(),
}));
vi.mock("@/lib/supabase/server", () => ({ getUser }));
vi.mock("@intervyn/ee", () => ({ gateRequest }));
vi.mock("@/lib/env", () => ({
  serverEnv: {
    agentApiUrl: "https://agent.example",
    internalApiSecret: "agent-test-secret",
    lightragApiSecret: "kb-test-secret",
  },
}));

const fetchMock = vi.fn<typeof fetch>();
const routes = [
  {
    name: "coach",
    post: coachPost,
    url: "https://agent.example/api/coach/chat",
    pathname: "/api/coach/chat",
    key: "session_id",
    secret: "agent-test-secret",
    schema: CoachReplySchema,
    reply: {
      answer: "Use STAR.",
      citations: [],
      follow_ups: ["What was the result?"],
    },
  },
  {
    name: "knowledge",
    post: kbPost,
    url: "https://kb.example/kb/query",
    pathname: "/api/kb/query",
    key: "user_id",
    secret: "kb-test-secret",
    schema: KbQueryResponseSchema,
    reply: { answer: "Use STAR.", citations: [] },
  },
];

function request(body: unknown) {
  return new Request("https://web.example/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  getUser.mockResolvedValue(null);
  gateRequest.mockReturnValue({ allow: true });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("LIGHTRAG_URL", "https://kb.example/");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe.each(routes)("$name API boundary", (route) => {
  it("rejects a denied distribution gate before calling an upstream", async () => {
    gateRequest.mockReturnValue({ allow: false });
    const response = await route.post(request({ query: "Help" }));
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "Sign in required" });
    expect(gateRequest).toHaveBeenCalledWith({
      pathname: route.pathname,
      isAuthenticated: false,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([{}, { query: "" }, { query: 42 }])(
    "rejects invalid request %j before calling an upstream",
    async (body) => {
      const response = await route.post(request(body));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("rejects malformed JSON", async () => {
    const response = await route.post(
      new Request("https://web.example/api/chat", {
        method: "POST",
        body: "{",
      }),
    );
    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards session scope, language and the service's private secret", async () => {
    getUser.mockResolvedValue({ id: "user-1" });
    fetchMock.mockResolvedValue(Response.json(route.reply));
    const response = await route.post(
      request({
        session_id: "sess_123",
        query: "How do I use STAR?",
        lang: "zh",
      }),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(route.reply);
    expect(gateRequest).toHaveBeenCalledWith({
      pathname: route.pathname,
      isAuthenticated: true,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      route.url,
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-internal-secret": route.secret,
        },
        body: JSON.stringify({
          [route.key]: "sess_123",
          query: "How do I use STAR?",
          lang: "zh",
        }),
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("defaults missing session scope and unsupported language", async () => {
    fetchMock.mockResolvedValue(Response.json(route.reply));
    await route.post(request({ query: "Help", lang: "unsupported" }));
    const init = fetchMock.mock.calls[0]?.[1];
    expect(JSON.parse(String(init?.body))).toEqual({
      [route.key]: "anonymous",
      query: "Help",
      lang: "en",
    });
  });

  it.each([
    "network",
    "timeout",
    "upstream-error",
    "invalid-json",
    "schema-drift",
  ])("returns a contract-valid fallback on %s", async (failure) => {
    if (failure === "network" || failure === "timeout") {
      fetchMock.mockRejectedValue(
        failure === "network"
          ? new TypeError("fetch failed")
          : new DOMException("Timed out", "TimeoutError"),
      );
    } else if (failure === "upstream-error") {
      fetchMock.mockResolvedValue(
        new Response("Service down", { status: 503 }),
      );
    } else if (failure === "invalid-json") {
      fetchMock.mockResolvedValue(new Response("<html>error</html>"));
    } else {
      fetchMock.mockResolvedValue(Response.json({ answer: 42 }));
    }
    const response = await route.post(request({ query: "Explain retries" }));
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(route.schema.safeParse(body).success).toBe(true);
    expect(body.answer).toContain("Explain retries");
    expect(JSON.stringify(body)).not.toContain(route.secret);
  });
});

it("knowledge chat works offline without making a fetch", async () => {
  vi.stubEnv("LIGHTRAG_URL", "");
  const response = await kbPost(request({ query: "Explain retries" }));
  expect(response.status).toBe(200);
  expect(KbQueryResponseSchema.safeParse(await response.json()).success).toBe(
    true,
  );
  expect(fetchMock).not.toHaveBeenCalled();
});
