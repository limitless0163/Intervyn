import "server-only";
import { serverEnv } from "@/lib/env";
import { SessionViewSchema, type SessionView } from "@/types/session";

/** Shared server read; a mismatched session must never authorize a room token. */
export async function loadSession(id: string): Promise<SessionView | null> {
  try {
    const res = await fetch(
      `${serverEnv.agentApiUrl.replace(/\/$/, "")}/api/session/${encodeURIComponent(id)}`,
      { cache: "no-store", signal: AbortSignal.timeout(15_000) },
    );
    if (!res.ok) return null;
    const parsed = SessionViewSchema.safeParse(await res.json());
    return parsed.success && parsed.data.session_id === id ? parsed.data : null;
  } catch {
    return null;
  }
}
