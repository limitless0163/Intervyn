import { z } from "zod";
import { cvContentType } from "@/lib/cv-upload";

const UploadSchema = z.object({
  uploadUrl: z.url({ protocol: /^https?$/ }),
  publicUrl: z.url({ protocol: /^https?$/ }),
});

export class CvUploadError extends Error {
  constructor(
    public readonly key: "fileReadError" | "uploadPrepareError" | "uploadError",
  ) {
    super(key);
  }
}

/** Preserve raw binary bytes and a useful MIME type in the storage-free path. */
export function fileToDataUrl(
  file: File,
  signal: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const reader = new FileReader();
    const abort = () => {
      reader.abort();
      reject(signal.reason);
    };
    signal.addEventListener("abort", abort, { once: true });
    reader.onloadend = () => signal.removeEventListener("abort", abort);
    reader.onload = () => {
      const result = String(reader.result);
      resolve(
        `data:${cvContentType(file)};base64,${result.slice(result.indexOf(",") + 1)}`,
      );
    };
    reader.onerror = () => reject(new CvUploadError("fileReadError"));
    reader.readAsDataURL(file);
  });
}

/** Presign then PUT with identical MIME types; both requests are cancellable. */
export async function uploadCv(
  file: File,
  signal: AbortSignal,
): Promise<string> {
  const contentType = cvContentType(file);
  let urls: z.infer<typeof UploadSchema>;
  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        content_type: contentType,
        size: file.size,
      }),
      signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    });
    if (!res.ok) throw new CvUploadError("uploadPrepareError");
    urls = UploadSchema.parse(await res.json());
  } catch {
    signal.throwIfAborted();
    throw new CvUploadError("uploadPrepareError");
  }
  try {
    const res = await fetch(urls.uploadUrl, {
      method: "PUT",
      headers: { "content-type": contentType },
      body: file,
      signal: AbortSignal.any([signal, AbortSignal.timeout(120_000)]),
    });
    if (!res.ok) throw new CvUploadError("uploadError");
    return urls.publicUrl;
  } catch {
    signal.throwIfAborted();
    throw new CvUploadError("uploadError");
  }
}
