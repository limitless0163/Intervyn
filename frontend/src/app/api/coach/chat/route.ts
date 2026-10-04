import { NextResponse } from "next/server";
import { z } from "zod";
import {
  CoachReplySchema,
  LanguageSchema,
  type CoachReply,
  type Language,
} from "@intervyn/shared";
import { gateRequest } from "@intervyn/ee";
import { serverEnv } from "@/lib/env";
import { getUser } from "@/lib/supabase/server";

// Reads server-only config (AGENT_API_URL) and proxies a live agent call.
export const dynamic = "force-dynamic";

/**
 * Client body. session_id is optional (the /prep surface may have no live
 * session); it only scopes knowledge retrieval. lang falls back to "en".
 */
const BodySchema = z.object({
  session_id: z.string().trim().min(1).max(256).default("anonymous"),
  query: z.string().trim().min(1).max(8000),
  lang: LanguageSchema.catch("en").default("en"),
});

/** A grounded mock reply so the coach chat works even with the agent down. */
function mockReply(query: string, lang: Language): CoachReply {
  const q = query.trim().replace(/\s+/g, " ");
  return lang === "zh"
    ? {
        answer: `关于“${q}”，先说明所用框架，再完整讲述一个具体例子，最后解释你选择的权衡。（示例回答：连接备考教练后，回答会结合你的资料。）`,
        citations: [],
        follow_ups: ["能举一个具体例子吗？", "这里最常见的错误是什么？"],
      }
    : {
        answer: `Here's how I'd coach you on "${q}": name the framework, walk one concrete example end to end, then state the trade-off you're optimizing for. (Sample response — connect the coach for answers grounded in your materials.)`,
        citations: [],
        follow_ups: [
          "Can you give a concrete example?",
          "What's a common mistake here?",
        ],
      };
}

export async function POST(request: Request) {
  // Distribution gate (no-op in OSS): coach replies spend LLM tokens; a
  // distribution with required auth rejects anonymous callers here.
  const user = await getUser();
  const gate = gateRequest({
    pathname: "/api/coach/chat",
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

  try {
    const secret = serverEnv.internalApiSecret;
    const upstream = await fetch(`${serverEnv.agentApiUrl}/api/coach/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(secret ? { "x-internal-secret": secret } : {}),
      },
      body: JSON.stringify({
        session_id: body.session_id,
        query: body.query,
        lang: body.lang,
      }),
      // Don't let a slow agent hang the request forever.
      signal: AbortSignal.timeout(30_000),
    });

    if (!upstream.ok)
      return NextResponse.json(mockReply(body.query, body.lang));

    const json = await upstream.json();
    const parsed = CoachReplySchema.safeParse(json);
    // Validate the upstream shape; fall back to a mock on drift.
    return NextResponse.json(
      parsed.success ? parsed.data : mockReply(body.query, body.lang),
    );
  } catch {
    // Agent unreachable / timeout / bad JSON — stay resilient.
    return NextResponse.json(mockReply(body.query, body.lang));
  }
}
