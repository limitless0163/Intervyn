import {
  KbQueryResponseSchema,
  type KbQueryResponse,
  type Citation,
  type Language,
} from "@intervyn/shared";

export type { KbQueryResponse, Citation };

/**
 * Ask the study coach's knowledge base a question. Always resolves to a grounded
 * answer + citations: the `/api/kb/query` route proxies to LightRAG when it is
 * configured and otherwise returns a sample answer. HTTP/network or contract
 * failures reject so callers can present an error and retry.
 */
export async function queryKnowledge(
  query: string,
  lang: Language = "en",
  sessionId = "anonymous",
  signal?: AbortSignal,
): Promise<KbQueryResponse> {
  const res = await fetch("/api/kb/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, query, lang }),
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(45_000)])
      : AbortSignal.timeout(45_000),
  });

  if (!res.ok) {
    throw new Error(`Knowledge query failed (${res.status})`);
  }

  return KbQueryResponseSchema.parse(await res.json());
}
