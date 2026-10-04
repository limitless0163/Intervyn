/** 服务端调用 Agent API 并校验共享响应契约；内部密钥不得通过浏览器转发。 */
import {
  PrepResponseSchema,
  ScoreResponseSchema,
  StudyPlanSchema,
  type PrepRequest,
  type PrepResponse,
  type ScoreCard,
  type ScoreRequest,
  type ScoreResponse,
  type StudyPlan,
} from "@intervyn/shared";
import { serverEnv } from "@/lib/env";

async function postJson<T>(
  path: string,
  body: unknown,
  parse: (data: unknown) => T,
): Promise<T> {
  const secret = serverEnv.internalApiSecret;
  const res = await fetch(`${serverEnv.agentApiUrl}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(secret ? { "x-internal-secret": secret } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Agent request ${path} failed: ${res.status} ${res.statusText}${
        text ? ` — ${text}` : ""
      }`,
    );
  }

  return parse(await res.json());
}

export function requestPrep(body: PrepRequest): Promise<PrepResponse> {
  return postJson("/api/prep", body, (d) => PrepResponseSchema.parse(d));
}

export function requestScore(body: ScoreRequest): Promise<ScoreResponse> {
  return postJson("/api/score", body, (d) => ScoreResponseSchema.parse(d));
}

export function requestCoachPlan(scorecard: ScoreCard): Promise<StudyPlan> {
  return postJson("/api/coach/plan", { scorecard }, (d) =>
    StudyPlanSchema.parse(d),
  );
}
