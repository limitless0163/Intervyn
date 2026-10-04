import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cvContentType,
  cvFileError,
  MAX_CV_BYTES,
} from "../../src/lib/cv-upload";
import { uploadCv } from "../../src/services/cv";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("CV files", () => {
  it.each([
    ["resume.PDF", "", "application/pdf"],
    [
      "resume.docx",
      "application/octet-stream",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    ["resume.txt", "", "text/plain"],
    ["resume.md", "", "text/markdown"],
    ["resume.pdf", "text/html", "text/html"],
    ["resume.exe", "", "application/octet-stream"],
  ])(
    "resolves %s (%s) without overriding explicit MIME types",
    (name, type, expected) => {
      expect(cvContentType({ name, type })).toBe(expected);
    },
  );

  it("uses the same decimal 10 MB ceiling as document extraction", () => {
    const file = {
      name: "cv.pdf",
      type: "application/pdf",
      size: MAX_CV_BYTES,
    };
    expect(cvFileError(file)).toBeNull();
    expect(cvFileError({ ...file, size: MAX_CV_BYTES + 1 })).toBe(
      "fileTooLarge",
    );
    expect(cvFileError({ ...file, size: 0 })).toBe("fileEmpty");
    expect(cvFileError({ ...file, type: "text/html" })).toBe("fileUnsupported");
  });
});

describe("CV upload", () => {
  const urls = {
    uploadUrl: "https://r2.example/upload",
    publicUrl: "https://files.example/cv.pdf",
  };
  const file = new File(["%PDF-1.7"], "cv.pdf");

  it("uses the same inferred MIME type for the presign and PUT", async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json(urls))
      .mockResolvedValueOnce(new Response());
    const controller = new AbortController();
    expect(await uploadCv(file, controller.signal)).toBe(urls.publicUrl);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      filename: "cv.pdf",
      content_type: "application/pdf",
      size: file.size,
    });
    expect(fetchMock.mock.calls[1]).toEqual([
      urls.uploadUrl,
      expect.objectContaining({
        headers: { "content-type": "application/pdf" },
        body: file,
        signal: expect.any(AbortSignal),
      }),
    ]);
    controller.abort();
    expect(fetchMock.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
    expect(fetchMock.mock.calls[1]?.[1]?.signal?.aborted).toBe(true);
  });

  it.each([
    { uploadUrl: "javascript:alert(1)", publicUrl: urls.publicUrl },
    { uploadUrl: urls.uploadUrl },
  ])(
    "rejects invalid presigned destinations before uploading",
    async (body) => {
      fetchMock.mockResolvedValue(Response.json(body));
      await expect(
        uploadCv(file, new AbortController().signal),
      ).rejects.toMatchObject({ key: "uploadPrepareError" });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it("maps a failed PUT to an actionable upload error", async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json(urls))
      .mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(
      uploadCv(file, new AbortController().signal),
    ).rejects.toMatchObject({ key: "uploadError" });
  });

  it("propagates navigation cancellation", async () => {
    const controller = new AbortController();
    controller.abort();
    fetchMock.mockRejectedValue(controller.signal.reason);
    await expect(uploadCv(file, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });
});
