import { NextResponse } from "next/server";
import { z } from "zod";
import {
  KbQueryResponseSchema,
  LanguageSchema,
  type KbQueryResponse,
  type Language,
} from "@intervyn/shared";
import { gateRequest } from "@intervyn/ee";
import { getUser } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";

// Reads server-only env (LIGHTRAG_URL) and the per-request user; never prerender.
export const dynamic = "force-dynamic";

/**
 * Incoming client body `{session_id?, query, lang}`; `session_id` defaults to
 * "anonymous" and `lang` falls back to "en". The knowledge store is keyed by
 * `session_id` (the same key the prep pipeline ingests under and the Study Coach
 * retrieves with) — the shared `KbQueryRequest` names this `store_key`. This
 * route forwards to the LightRAG sidecar, whose own request model still names
 * the partition key `user_id`, so we send `user_id: session_id` below.
 */
const BodySchema = z.object({
  session_id: z.string().trim().min(1).max(256).default("anonymous"),
  query: z.string().trim().min(1).max(8000),
  lang: LanguageSchema.catch("en").default("en"),
});

/** A grounded mock answer so the coach chat works fully offline. */
function mockAnswer(query: string, lang: Language): KbQueryResponse {
  const q = query.trim().replace(/\s+/g, " ");
  return {
    answer:
      lang === "zh"
        ? `关于“${q}”，用具体例子组织你的回答，说明关键概念之间的联系，并解释所做的权衡。（示例回答：连接知识库后，回答会结合你的资料并附上来源。）`
        : `Here's a take on "${q}": anchor your answer in a concrete example, explain how the key concepts relate, and name the trade-off you're optimizing for. (Sample response — connect the knowledge service for answers and citations grounded in your own notes.)`,
    citations: [],
  };
}

export async function POST(request: Request) {
  // Resolve the user server-side; anonymous when there's no session. The
  // distribution gate (no-op in OSS) runs before any work — including the
  // offline mock — so required-auth distributions are consistent here.
  const user = await getUser();
  const gate = gateRequest({
    pathname: "/api/kb/query",
    isAuthenticated: Boolean(user),
  });
  if (!gate.allow) {
    return NextResponse.json({ error: "Sign in required" }, { status: 401 });
  }

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await request.json());
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 },
    );
  }

  const lightragUrl = process.env.LIGHTRAG_URL;

  // Offline / unconfigured: return a grounded mock so the chat always works.
  if (!lightragUrl) {
    return NextResponse.json(mockAnswer(body.query, body.lang));
  }

  try {
    const secret = serverEnv.lightragApiSecret;
    const upstream = await fetch(`${lightragUrl.replace(/\/$/, "")}/kb/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(secret ? { "x-internal-secret": secret } : {}),
      },
      // Scope retrieval by session_id — the key the prep pipeline ingested
      // under and the agent coach queries with — so the docs are reachable.
      body: JSON.stringify({
        user_id: body.session_id,
        query: body.query,
        lang: body.lang,
      }),
      // Don't let a slow RAG backend hang the request forever.
      signal: AbortSignal.timeout(30_000),
    });

    if (!upstream.ok)
      return NextResponse.json(mockAnswer(body.query, body.lang));

    const json = await upstream.json();
    const parsed = KbQueryResponseSchema.safeParse(json);
    // Shape/validate upstream output; fall back to mock on drift.
    return NextResponse.json(
      parsed.success ? parsed.data : mockAnswer(body.query, body.lang),
    );
  } catch {
    // Network error, timeout, bad JSON — stay resilient.
    return NextResponse.json(mockAnswer(body.query, body.lang));
  }
}
