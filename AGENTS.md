# Repository agent guide

## Project and service topology

Intervyn is a pnpm/Turborepo workspace for the Next.js web app, shared TypeScript contracts, CLI, and Python agent. The runtime services are:

- `frontend/`: Next.js App Router UI and server handlers. Server handlers call the agent and knowledge service; browser code must not call those services with private credentials.
- `backend/app/`: FastAPI agent API for prep, coaching, scoring, session state, and traces. `backend/app/services/live/worker.py` is a separate LiveKit voice worker.
- `backend/services/lightrag/`: standalone FastAPI knowledge sidecar on port 9621, with its own `uv` project.
- Supabase Auth/Postgres and Cloudflare R2 are optional integrations. The agent uses in-process memory storage unless both Supabase URL and service-role key are configured.
- `docker-compose.yml` starts the web, agent API, and knowledge sidecar. The voice worker is in the `live` profile; local Ollama/Whisper/Kokoro services are in the `local` profile.

## Repository map

- `frontend/src/app/`: pages, Server Actions, and Next route handlers; `components/`, `features/`, `hooks/`, `lib/`, `services/`, `styles/`, `types/`, and `utils/` hold UI and app code.
- `frontend/packages/shared/src/`: Zod wire contracts; `schema/` contains generated JSON Schemas and `fixtures/` contains contract fixtures.
- `frontend/packages/ee/`: OSS distribution seam with inert feature flags and request gate.
- `frontend/cli/`: `intervyn` CLI source and avatar manifest.
- `backend/app/`: API, configuration/adapters, dependencies, repository, Pydantic schemas, and coach/live/post/prep/skilllib services.
- `backend/skills/`: curated skill packs and generated index; `_review/` is a transient draft queue.
- `backend/services/lightrag/`: independent knowledge sidecar project; tests live at `backend/tests/lightrag/`.
- `infra/supabase/migrations/`: ordered SQL migrations. `scripts/`: repository setup and auxiliary scripts. `.github/workflows/ci.yml`: CI contract.

`docs/instructions/ARCHITECTURE_INSTRUCTIONS.md` contains an example target tree that does not match this checkout (including paths such as root `tests/`, `Makefile`, and backend `db/`/`models/`). Use the actual source tree and module guides below when locating code; do not create or move files just to match that example.

## Prerequisites and root commands

- Use Node 22 (`.nvmrc`), pnpm 11.5.2 (`package.json`), Python 3.11+ (`backend/pyproject.toml`), and `uv`.
- From the repository root, `bash scripts/setup.sh` installs the pnpm workspace and syncs the backend Python environment. Then run `pnpm build && pnpm intervyn init` to build the CLI before using its setup wizard; `init` scaffolds root `.env`, `backend/.env`, and `frontend/.env.local` from the root template.
- `pnpm dev` runs workspace development tasks; only the web package currently defines `dev`, so it does not start the Python API or LiveKit worker.
- Root validation commands: `pnpm build`, `pnpm typecheck`, `pnpm test`, `pnpm lint`, and `pnpm gen:schema`. `pnpm lint` checks the configured frontend files with Prettier and runs backend Ruff. The knowledge sidecar is a separate `uv` project; run its tests with `uv --directory backend/services/lightrag run pytest`.
- Base stack: `docker compose up --build`. Add `--profile live` for the voice worker (requires LiveKit and voice-provider configuration); add `--profile local` for local model servers.
- After a run, use `pnpm intervyn traces` and `pnpm intervyn traces show <trace-id>` to inspect local traces. Build first so `frontend/cli/dist/index.js` exists. Traces default to `.intervyn/traces`; prompt previews are off by default.

## Cross-cutting rules

- Shared wire contracts are authored in `frontend/packages/shared/src/`. Regenerate `frontend/packages/shared/schema/` with `pnpm gen:schema`; do not hand-edit generated schemas. Mirror wire fields in `backend/app/schemas/shared_models.py`; `backend/tests/test_parity.py` checks the contract.
- Use root `.env.example` as the environment-variable template. Keep real credentials in ignored `.env` files, never commit them. `NEXT_PUBLIC_*` values are compiled into the browser bundle at build time; keep private values in server-only configuration.
- Add database changes as new ordered SQL files under `infra/supabase/migrations/`; preserve already-applied migration history.
- Keep operational coding-agent guidance in `AGENTS.md` files. The `CLAUDE.md` files are import-only shims.
- Follow the module-specific rules in [frontend/AGENTS.md](frontend/AGENTS.md) and [backend/AGENTS.md](backend/AGENTS.md).

## CI and deployment

`.github/workflows/ci.yml` generates/checks schemas, builds, typechecks, lints, runs workspace tests and sidecar tests, validates Compose profiles, and builds Docker images. `.github/workflows/deploy.yml` is manually triggered and still contains placeholder/commented deployment commands; do not treat it as a completed production deploy path.
