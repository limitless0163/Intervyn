import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fileToDataUrl, uploadCv } from "../../src/services/cv";

const fetchMock = vi.fn<typeof fetch>();
const urls = {
  uploadUrl: "https://storage.example/put?signature=test",
  publicUrl: "https://storage.example/cv.pdf",
};
const file = new File([new Uint8Array([0, 255, 37, 80, 68, 70])], "CV.PDF", {
  type: "application/octet-stream",
});

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("presigned CV upload", () => {
  it.each(["http", "network", "invalid-json"])(
    "does not PUT when preparation fails (%s)",
    async (failure) => {
      if (failure === "network")
        fetchMock.mockRejectedValue(new TypeError("fetch failed"));
      else if (failure === "http")
        fetchMock.mockResolvedValue(new Response(null, { status: 501 }));
      else if (failure === "invalid-json")
        fetchMock.mockResolvedValue(new Response("{"));
      await expect(
        uploadCv(file, new AbortController().signal),
      ).rejects.toMatchObject({ key: "uploadPrepareError" });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it("reports a rejected PUT", async () => {
    fetchMock.mockResolvedValueOnce(Response.json(urls));
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 403 }));
    await expect(
      uploadCv(file, new AbortController().signal),
    ).rejects.toMatchObject({ key: "uploadError" });
  });

  it.each(["prepare", "put"])(
    "propagates user cancellation during %s",
    async (stage) => {
      const controller = new AbortController();
      if (stage === "put") fetchMock.mockResolvedValueOnce(Response.json(urls));
      fetchMock.mockImplementationOnce(async () => {
        controller.abort();
        throw controller.signal.reason;
      });
      await expect(uploadCv(file, controller.signal)).rejects.toMatchObject({
        name: "AbortError",
      });
      expect(fetchMock).toHaveBeenCalledTimes(stage === "put" ? 2 : 1);
    },
  );
});

describe("storage-free file reading", () => {
  // FileReader is a browser boundary. Control only its load/error/abort events.
  function readerMock() {
    const reader = {
      result: null as string | null,
      onload: null as (() => void) | null,
      onerror: null as (() => void) | null,
      onloadend: null as (() => void) | null,
      abort: vi.fn(),
      readAsDataURL: vi.fn(),
    };
    vi.stubGlobal(
      "FileReader",
      class {
        constructor() {
          return reader;
        }
      },
    );
    return reader;
  }

  it("preserves binary payload and repairs the generic browser MIME", async () => {
    const reader = readerMock();
    const controller = new AbortController();
    const pending = fileToDataUrl(file, controller.signal);
    reader.result = "data:application/octet-stream;base64,AP8lUERG";
    reader.onload?.();
    reader.onloadend?.();
    expect(await pending).toBe("data:application/pdf;base64,AP8lUERG");
    expect(reader.readAsDataURL).toHaveBeenCalledWith(file);
    controller.abort();
    expect(reader.abort).not.toHaveBeenCalled();
  });

  it("turns read errors into a displayable error and removes the listener", async () => {
    const reader = readerMock();
    const controller = new AbortController();
    const pending = fileToDataUrl(file, controller.signal);
    reader.onerror?.();
    reader.onloadend?.();
    await expect(pending).rejects.toMatchObject({ key: "fileReadError" });
    controller.abort();
    expect(reader.abort).not.toHaveBeenCalled();
  });

  it("aborts an active reader when the user cancels", async () => {
    const reader = readerMock();
    const controller = new AbortController();
    const pending = fileToDataUrl(file, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(reader.abort).toHaveBeenCalledOnce();
  });

  it("does not start reading an already cancelled file", async () => {
    const reader = readerMock();
    const controller = new AbortController();
    controller.abort();
    await expect(fileToDataUrl(file, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(reader.readAsDataURL).not.toHaveBeenCalled();
  });
});
