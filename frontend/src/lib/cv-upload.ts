/** Matches the agent's document extraction limit (10 MB, in bytes). */
export const MAX_CV_BYTES = 10_000_000;
export const MIN_CV_CHARS = 30;
export const MIN_JD_CHARS = 40;

export const CV_CONTENT_TYPES = new Set([
  "application/pdf",
  "application/x-pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "text/plain",
  "text/markdown",
]);

const EXTENSION_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  doc: "application/msword",
  txt: "text/plain",
  md: "text/markdown",
};

/** Some browsers supply an empty or generic MIME type for document files. */
export function cvContentType(file: { name: string; type: string }): string {
  const type = (file.type.split(";", 1)[0] ?? "").trim().toLowerCase();
  if (type && type !== "application/octet-stream") return type;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return EXTENSION_TYPES[extension] ?? "application/octet-stream";
}

export function cvFileError(file: {
  name: string;
  type: string;
  size: number;
}): "fileEmpty" | "fileTooLarge" | "fileUnsupported" | null {
  if (file.size === 0) return "fileEmpty";
  if (file.size > MAX_CV_BYTES) return "fileTooLarge";
  if (!CV_CONTENT_TYPES.has(cvContentType(file))) return "fileUnsupported";
  return null;
}
