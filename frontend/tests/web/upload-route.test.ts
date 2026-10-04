import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "../../src/app/api/upload/route";
import { MAX_CV_BYTES } from "../../src/lib/cv-upload";

const {
  getUser,
  gateRequest,
  isR2Configured,
  isSupabaseConfigured,
  presignUpload,
} = vi.hoisted(() => ({
  getUser: vi.fn(),
  gateRequest: vi.fn(),
  isR2Configured: vi.fn(),
  isSupabaseConfigured: vi.fn(),
  presignUpload: vi.fn(),
}));
vi.mock("@/lib/supabase/server", () => ({ getUser }));
vi.mock("@intervyn/ee", () => ({ gateRequest }));
vi.mock("@/lib/env", () => ({ isR2Configured, isSupabaseConfigured }));
vi.mock("@/lib/r2", () => ({ presignUpload }));

const valid = { filename: "cv.pdf", content_type: "application/pdf", size: 10 };
const urls = {
  uploadUrl: "https://storage.example/upload?signature=test",
  publicUrl: "https://storage.example/cv.pdf",
};
function request(body: unknown) {
  return new Request("https://web.example/api/upload", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  getUser.mockResolvedValue(null);
  gateRequest.mockReturnValue({ allow: true });
  isSupabaseConfigured.mockReturnValue(false);
  isR2Configured.mockReturnValue(true);
  presignUpload.mockResolvedValue(urls);
});

describe("CV upload API", () => {
  it.each(["auth", "distribution"])(
    "denies %s before signing",
    async (gate) => {
      if (gate === "auth") isSupabaseConfigured.mockReturnValue(true);
      else gateRequest.mockReturnValue({ allow: false });
      expect((await POST(request(valid))).status).toBe(401);
      expect(presignUpload).not.toHaveBeenCalled();
    },
  );

  it.each([
    {},
    { ...valid, filename: "" },
    { ...valid, content_type: "" },
    { ...valid, size: 0 },
    { ...valid, size: -1 },
    { ...valid, size: 1.5 },
    { ...valid, size: "10" },
    { ...valid, size: MAX_CV_BYTES + 1 },
  ])("rejects invalid metadata %j", async (body) => {
    expect((await POST(request(body))).status).toBe(400);
    expect(presignUpload).not.toHaveBeenCalled();
  });

  it("rejects malformed JSON", async () => {
    const response = await POST(
      new Request("https://web.example/api/upload", {
        method: "POST",
        body: "{",
      }),
    );
    expect(response.status).toBe(400);
    expect(presignUpload).not.toHaveBeenCalled();
  });

  it("rejects unsupported content even with a PDF filename", async () => {
    expect(
      (await POST(request({ ...valid, content_type: "text/html" }))).status,
    ).toBe(415);
    expect(presignUpload).not.toHaveBeenCalled();
  });

  it("reports missing storage configuration without signing", async () => {
    isR2Configured.mockReturnValue(false);
    expect((await POST(request(valid))).status).toBe(501);
    expect(presignUpload).not.toHaveBeenCalled();
  });

  it("accepts the size boundary, sanitizes paths and generates unique keys", async () => {
    getUser.mockResolvedValue({ id: "owner" });
    isSupabaseConfigured.mockReturnValue(true);
    const body = {
      ...valid,
      filename: "folder/cv\\resume.pdf",
      size: MAX_CV_BYTES,
      content_type: "Application/PDF; charset=binary",
    };
    for (let i = 0; i < 2; i++) {
      const response = await POST(request(body));
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual(urls);
    }
    const keys = presignUpload.mock.calls.map(([key]) => key);
    expect(keys[0]).toMatch(/^uploads\/[0-9a-f-]{36}-folder_cv_resume\.pdf$/);
    expect(keys[0]).not.toBe(keys[1]);
    expect(presignUpload).toHaveBeenCalledWith(
      keys[0],
      body.content_type,
      MAX_CV_BYTES,
    );
    expect(gateRequest).toHaveBeenCalledWith({
      pathname: "/api/upload",
      isAuthenticated: true,
    });
  });

  it("does not expose storage credentials on signing failure", async () => {
    presignUpload.mockRejectedValue(new Error("private-storage-secret"));
    const response = await POST(request(valid));
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      error: "Upload could not be prepared",
    });
  });
});
