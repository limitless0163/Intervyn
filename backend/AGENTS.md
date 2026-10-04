# Backend agent guide

See the [repository guide](../AGENTS.md) for workspace topology, root setup, shared-contract policy, migrations, and CI. This guide covers the Python agent API, LiveKit worker, skill library, and the separate knowledge sidecar.

## Stack and commands

- The agent is Python 3.11+ with FastAPI, Pydantic 2, `pydantic-settings`, LangGraph, and `uv`. Main dependencies and optional provider groups are in `pyproject.toml`; the lockfile is `uv.lock`.
- From `backend/`, use `uv sync`, `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`, `uv run pytest -q`, and `uv run ruff check .`. From the repository root, the workspace wrappers are `pnpm --filter @intervyn/agent test` and `pnpm --filter @intervyn/agent lint`.
- `backend/services/lightrag/` is a separate `uv` project with its own `pyproject.toml` and `uv.lock`. Its offline test command from the root is `uv --directory backend/services/lightrag run pytest`; its Ruff command is `uv --directory backend/services/lightrag run ruff check .`. The optional heavy `rag` extra is required only for `RAG_BACKEND=lightrag`.

## Architecture and boundaries

- `app/main.py` creates the FastAPI app and registers `app/api/router.py`. Route handlers in `app/api/routes/` own HTTP request/response behavior; business flows belong in `app/services/`.
- `app/core/` holds settings, logging, tracing, observability, and provider adapters. `app/dependencies/container.py` assembles/caches adapters and repository into `Deps`; use its protocol-based adapters and repository rather than constructing providers inside routes/services.
- `app/repositories/repository.py` defines `SessionRepository`, the default process-wide `MemoryRepository`, and optional `SupabaseRepository`. Supabase persistence is selected only when both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set; memory state is lost on process restart and is not shared across processes.
- `app/schemas/shared_models.py` mirrors the TypeScript/Zod contracts. API-only read models live in `app/schemas/views.py`; internal worker payloads such as `LiveResultRequest` intentionally stay out of the shared parity registry.
- `app/services/prep/` is a LangGraph fan-out (CV analysis, JD analysis, company research) followed by gap matching and question planning. `post/` evaluates and reports scores; `coach/` handles study planning/chat; `live/` contains LiveKit interview state, director, tools, guard, transcript flusher, and worker; `skilllib/` manages skill packs.
- API routes include prep, score, coach, knowledge, session/live-result, and traces. `/health` is the agent health check. The session view is read by an unguessable session id; internal write/compute paths use the optional secret gate.
- `services/lightrag/src/lightrag_service/` is an independent FastAPI app. `NaiveRAG` is the default deterministic in-memory per-user store; the real LightRAG stack is optional. Do not describe or rely on the default sidecar as persistent storage.

## Invariants to preserve

- Treat `frontend/packages/shared/src/` as the wire-contract source. Match field names, required/default behavior, and model registry in `app/schemas/shared_models.py`; generated JSON Schemas live in `../frontend/packages/shared/schema/`. Run `pnpm gen:schema` from the repo root after contract edits and keep `backend/tests/test_parity.py` passing.
- Prep step names/order and the graph join are consumed by progress reporting. Update `app/services/prep/graph.py`, nodes/state, view models, and tests together when changing the pipeline.
- Keep interview `transcript` and study-coach `coach_transcript` separate (`infra/supabase/migrations/0004_coach_transcript.sql`). The LiveKit worker periodically checkpoints transcript/context off the turn path and writes final state during shutdown; preserve write-back and recovery behavior.
- `SessionGuard` is the live-session backstop: defaults are 2,400 seconds, 80 transcript turns, and a bounded 300-second answer grace. At a limit it stops new questions while allowing the active answer to finish within that grace. Keep guard, progression, persistence, and shutdown behavior coordinated.
- Scoring is serialized per session and already-complete sessions return their stored scorecard. A session with no answers reaches `no_answers` and must not receive a misleading zero scorecard. Preserve degraded/fallback scoring behavior on provider failures.
- Adaptive difficulty, score verification, skill distillation, BVC noise cancellation, hosted tracing, and real LightRAG are gated/optional in settings or extras. Keep their defaults and offline mock behavior unless the task explicitly changes them.
- `INTERNAL_API_SECRET`, when configured, must be shared by the web app, worker, and agent API; guarded agent writes use `X-Internal-Secret`. `LIGHTRAG_API_SECRET` is a separate sidecar secret. Preserve constant-time secret comparison and sidecar SSRF protections: reject non-HTTP(S), literal private/loopback hosts, and redirects. Hostnames are not DNS-resolved by the guard.
- Skill proposals go to `backend/skills/_review/`; they are never auto-promoted. Do not commit real candidate drafts. Packs must stay generalized and de-identified; promotion re-scrubs PII. Regenerate the pack index with `uv --directory backend run python -m scripts.gen_skill_index`; validate with `pnpm build` followed by `pnpm intervyn skills lint`.
- Add Supabase schema changes as new ordered SQL files in `../infra/supabase/migrations/`; do not rewrite applied migrations. Keep RLS and user ownership semantics intact.

## Configuration, logging, and style

- `Settings` in `app/core/config.py` reads `.env` from the process working directory and ignores unknown keys. Run local agent commands from `backend/`; the setup CLI scaffolds `backend/.env`. Provider selection defaults to deterministic mocks when no real provider is configured. Add documented variables to the root `.env.example` and settings model together.
- The optional `livekit`, `supabase`, provider, and `observability` dependency groups are defined in `pyproject.toml`. The API Docker target omits the heavy LiveKit group; the worker target includes it. Preserve the `live` Compose profile and target separation.
- Local JSONL traces default to `.intervyn/traces`; `TRACE_ENABLED=0` disables them. Prompt capture is off by default (`TRACE_INCLUDE_PROMPTS=0`) because prompts can contain CV/JD data. Tracing/observability failures must not break API, prep, scoring, or live turns. Use `app/core/logging.py` for named loggers and `intervyn traces` for local inspection.
- Ruff is configured with a 100-character line length. Follow the existing async style, typed protocols, Pydantic `extra="forbid"` wire models, and narrow exception handling/fallback behavior in the touched subsystem.
- Agent tests are in `backend/tests/`; sidecar tests are in `backend/tests/lightrag/`. The main `pnpm test` includes the agent package but not the separate sidecar project.
