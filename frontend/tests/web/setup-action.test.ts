import { beforeEach, expect, it, vi } from "vitest";
import { startSession } from "../../src/app/setup/actions";
import type { PrepRequest } from "@intervyn/shared";

const { requestPrep, getUser, isSupabaseConfigured, features } = vi.hoisted(
  () => ({
    requestPrep: vi.fn(),
    getUser: vi.fn(),
    isSupabaseConfigured: vi.fn(),
    features: { auth: false },
  }),
);
vi.mock("@/services/api", () => ({ requestPrep }));
vi.mock("@/lib/supabase/server", () => ({ getUser }));
vi.mock("@/lib/env", () => ({ isSupabaseConfigured }));
vi.mock("@intervyn/ee", () => ({ features }));
const input: PrepRequest = {
  cv_url: "Experienced engineer in frontend architecture and accessibility.",
  jd_text:
    "Seeking a frontend engineer with strong React and TypeScript experience.",
  company: "",
  language_mode: { primary: "en", mixed: false },
};
beforeEach(() => {
  vi.resetAllMocks();
  features.auth = false;
  isSupabaseConfigured.mockReturnValue(false);
  requestPrep.mockResolvedValue({ session_id: "session-1" });
});

it.each([
  { ...input, cv_url: " " },
  { ...input, jd_text: "short" },
  { ...input, language_mode: { primary: "unsupported", mixed: false } },
  null,
])(
  "rejects invalid direct action input before calling the agent",
  async (value) => {
    expect(await startSession(value as PrepRequest)).toMatchObject({
      ok: false,
      reason: "invalid_input",
    });
    expect(requestPrep).not.toHaveBeenCalled();
  },
);
it("does not trust client-supplied session ownership", async () => {
  isSupabaseConfigured.mockReturnValue(true);
  getUser.mockResolvedValue({ id: "signed-in-user" });
  expect(await startSession({ ...input, user_id: "spoofed-user" })).toEqual({
    ok: true,
    session_id: "session-1",
  });
  expect(requestPrep).toHaveBeenCalledWith({
    ...input,
    user_id: "signed-in-user",
  });
});
it("allows anonymous OSS use and strips spoofed ownership", async () => {
  await startSession({ ...input, user_id: "spoofed-user" });
  expect(requestPrep).toHaveBeenCalledWith({ ...input, user_id: undefined });
});
it("preserves required-auth distributions", async () => {
  features.auth = true;
  expect(await startSession(input)).toMatchObject({
    ok: false,
    reason: "auth_required",
  });
  expect(requestPrep).not.toHaveBeenCalled();
});
it("accepts a short valid CV URL rather than applying the pasted-text minimum", async () => {
  expect(
    await startSession({ ...input, cv_url: "https://a.b/c.pdf" }),
  ).toMatchObject({ ok: true });
});
it("returns a recoverable error without leaking an upstream response", async () => {
  requestPrep.mockRejectedValue(new Error("private upstream details"));
  const result = await startSession(input);
  expect(result).toMatchObject({ ok: false, reason: "service_unavailable" });
  expect(JSON.stringify(result)).not.toContain("private upstream details");
});
it("handles auth service failures without leaving the caller's loading state stuck", async () => {
  isSupabaseConfigured.mockReturnValue(true);
  getUser.mockRejectedValue(new TypeError("offline"));
  expect(await startSession(input)).toMatchObject({
    ok: false,
    reason: "service_unavailable",
  });
});
