import { beforeEach, vi } from "vitest";

// Each test opts into its own provider configuration and HTTP responses.
beforeEach(() => {
  for (const key of [
    "NEXT_PUBLIC_APP_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "AGENT_API_URL",
    "INTERNAL_API_SECRET",
    "LIGHTRAG_URL",
    "LIGHTRAG_API_SECRET",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "LIVEKIT_AGENT_NAME",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_URL",
  ]) {
    vi.stubEnv(key, "");
  }
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("Network disabled in tests; provide a fetch mock.");
    }),
  );
});
