# Backend

`backend/` contains the FastAPI agent API, its prep/coaching/scoring services, a separate LiveKit voice worker, curated skill packs, and the independently managed knowledge sidecar in `services/lightrag/`.

## Architecture

- `app/main.py` creates the FastAPI app and exposes `/health`; `app/api/routes/` contains prep, score, coach, knowledge, session, and trace handlers.
- `app/services/prep/` builds interview context and a question plan. `post/` scores completed sessions and assembles reports. `coach/` builds study plans and coaching replies.
- `app/services/live/worker.py` is the separate LiveKit Agents worker. It joins rooms, runs the live interview loop, and writes session results back to the API.
- `app/core/` holds settings, provider adapters, logging, traces, and observability. `app/dependencies/container.py` assembles adapters and the session repository.
- `services/lightrag/` is a separate FastAPI project. Its default `NaiveRAG` backend is in-memory; the optional LightRAG implementation requires the `rag` extra.

## Stack

- Python 3.11+, FastAPI, Pydantic 2, `pydantic-settings`, and Uvicorn.
- LangGraph and LangChain Core for the preparation workflow.
- `uv` for dependency and environment management; pytest and Ruff for development.
- LiveKit Agents, Supabase, provider SDKs, and hosted observability are optional dependency groups in `pyproject.toml`.

## Prerequisites and Installation

Install Python 3.11+ and `uv`. From `backend/`:

```bash
uv sync
```

The settings loader reads `.env` from the process working directory. The root `pnpm --dir frontend intervyn init` command can create `backend/.env` from the root `.env.example`.

## Run

Start the agent API from `backend/`:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The health endpoint is `/health`. The API uses mock provider adapters by default when no real provider is configured. Session state uses an in-process memory repository unless both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set; memory state is lost when the process stops and is not shared across processes.

The knowledge sidecar is a separate project. From `backend/services/lightrag/`:

```bash
uv sync
uv run python -m lightrag_service.app
```

It listens on port `9621` by default. See [the sidecar guide](services/lightrag/README.md) for its optional LightRAG setup. From the repository root, `docker compose up --build` starts the web app, agent API, and sidecar; the separate voice worker is included with `docker compose --profile live up --build`.

## API Routes

| Route | Purpose |
| --- | --- |
| `GET /health` | Health check |
| `POST /api/prep` | Prepare an interview plan |
| `POST /api/score`, `POST /api/score/start` | Score a session synchronously or in the background |
| `POST /api/coach/plan`, `POST /api/coach/chat` | Create a study plan and coaching response |
| `POST /api/kb/ingest`, `POST /api/kb/query` | Add and query knowledge sources |
| `GET /api/session/{session_id}` | Read a session view |
| `POST /api/session/{session_id}/live-result` | Write back a completed live interview |
| `GET /api/traces`, `GET /api/traces/{trace_id}` | Read local trace data |

When `INTERNAL_API_SECRET` is set, guarded prep, score, coach, knowledge, and live-result operations require the matching `X-Internal-Secret` header. `LIGHTRAG_API_SECRET` is a separate sidecar secret.

## Configuration

The root [`.env.example`](../.env.example) is the variable template. Common settings:

| Variables | Purpose |
| --- | --- |
| `LLM_PROVIDER`, `STT_PROVIDER`, `TTS_PROVIDER`, `SEARCH_PROVIDER`, `EMBEDDINGS_PROVIDER` | Select provider adapters; the settings defaults are mock, while the root env template selects providers for some stages |
| Provider API keys such as `GEMINI_API_KEY`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `TAVILY_API_KEY` | Credentials for selected external providers |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME` | Voice transport and worker dispatch |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Enable Supabase session persistence when both are set |
| `LIGHTRAG_URL`, `LIGHTRAG_API_SECRET` | Connect the API to the knowledge sidecar |
| `RAG_BACKEND` | Sidecar backend selection (`naive` by default; see the [sidecar guide](services/lightrag/README.md)) |
| `INTERNAL_API_SECRET` | Optional guard for internal write and compute routes |
| `TRACE_ENABLED`, `TRACE_DIR`, `TRACE_INCLUDE_PROMPTS` | Local JSONL traces and optional prompt previews |

Prompt capture is off by default. Treat trace files as potentially sensitive if prompt capture is enabled.

## Tests and Code Style

From `backend/`:

```bash
uv run pytest -q
uv run ruff check .
```

The knowledge sidecar has its own lockfile and test command. From the repository root:

```bash
uv --directory backend/services/lightrag run pytest
uv --directory backend/services/lightrag run ruff check .
```

The root workspace wrappers are `pnpm --dir frontend --filter @intervyn/agent test` and `pnpm --dir frontend --filter @intervyn/agent lint`. Ruff uses a 100-character line length. Shared request and response models are mirrored from `frontend/packages/shared/src/` in `app/schemas/shared_models.py`; regenerate JSON Schemas from the repository root with `pnpm --dir frontend gen:schema` after contract changes.

## Source Layout

```text
app/api/routes/       HTTP route handlers
app/core/             Settings, adapters, logging, and observability
app/dependencies/     Dependency container and auth dependencies
app/repositories/     Session persistence interfaces and implementations
app/schemas/          Shared Pydantic models and API view models
app/services/         Prep, live, post, coach, and skill-library workflows
services/lightrag/    Standalone knowledge-sidecar project
skills/               Curated interview skill packs
tests/                Agent API, service, and parity tests
```
