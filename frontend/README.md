# Frontend

The `frontend/` workspace contains the Intervyn web app, shared TypeScript contracts, the OSS extension seam, and the `intervyn` CLI. Browser code talks to the agent and knowledge services through Next.js server routes; private service credentials stay server-side.

## Stack

- Next.js 16 App Router, React 19, TypeScript 5.9, and Tailwind CSS 4.
- Zod schemas in `packages/shared/` define the shared wire contracts; JSON Schema files are generated from them.
- Vitest runs the web, CLI, and shared-package tests in the Node environment.
- The `@intervyn/ee` package is an inert OSS extension seam.

## Prerequisites and Setup

Use Node 22 (`../.nvmrc`) and pnpm 11.5.2 (`../package.json`). From the repository root:

```bash
bash scripts/setup.sh
pnpm build
pnpm intervyn init
```

The setup script installs the workspace and syncs the Python agent environment. The CLI initializer writes the root `.env` and copies it to `backend/.env` and `frontend/.env.local`. Choose **Offline demo** for mock providers without provider keys. Docker Compose reads the root `.env`; local Next.js development reads `frontend/.env.local`.

## Run and Build

Run the web app from the repository root:

```bash
pnpm --filter @intervyn/web dev
```

The web dev server is only the frontend. Start the agent API separately from `backend/`:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For a full local stack, use `docker compose up --build` from the repository root. The voice worker is separate and requires LiveKit and voice-provider configuration: `docker compose --profile live up --build`.

| Command (from repository root) | Purpose |
| --- | --- |
| `pnpm build` | Build workspace packages and applications |
| `pnpm --filter @intervyn/web typecheck` | Generate route types and type-check the app |
| `pnpm --filter @intervyn/web test` | Run frontend Vitest tests |
| `pnpm --filter @intervyn/shared gen:schema` | Regenerate JSON Schemas from the Zod contracts |
| `pnpm --filter @intervyn/cli build` | Build the CLI used by `pnpm intervyn` |

Build the workspace before using `pnpm intervyn`; the root command runs `frontend/cli/dist/index.js`.

## Routes

| Path | Purpose |
| --- | --- |
| `/` | Landing page |
| `/setup` | Enter a CV and job description and prepare an interview |
| `/prep` | Study plan and prep coaching |
| `/interview/[id]` | Interview room |
| `/session/[id]` | Session progress view |
| `/report/[id]` | Interview report |
| `/avatars` | Avatar gallery |
| `/login`, `/signup` | Supabase sign-in pages when configured |

Server API routes include `/api/health`, `/api/session/[id]`, `/api/coach/chat`, `/api/kb/query`, and `/api/upload`.

## Configuration

Use the root [`.env.example`](../.env.example) as the variable list. `pnpm intervyn init` creates app-local env files. Values prefixed with `NEXT_PUBLIC_` are included in the browser bundle at build time; keep service credentials in server-only variables.

| Variables | Purpose |
| --- | --- |
| `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_SITE_URL` | Public app and metadata URLs |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Optional Supabase auth and server access |
| `AGENT_API_URL` | Agent API base URL; defaults to `http://localhost:8000` in the web server |
| `INTERNAL_API_SECRET` | Optional shared secret for guarded agent writes |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME` | LiveKit room tokens and worker dispatch |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL` | Optional CV object storage |
| `LIGHTRAG_URL`, `LIGHTRAG_API_SECRET` | Optional knowledge sidecar connection |
| `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE` | Optional error and trace reporting |

The frontend reads private upstream configuration in server code. Do not expose the agent API or sidecar credentials in Client Components.

## Source Layout

```text
src/app/                 Pages, Server Actions, and API routes
src/components/          UI grouped by product area
src/features/            Feature-specific client logic
src/lib/                 Environment, auth, localization, and integrations
src/services/             Server-side calls to agent and knowledge services
cli/                      `intervyn` setup and maintenance commands
packages/shared/src/      Zod wire contracts
packages/shared/schema/   Generated JSON Schemas
packages/ee/              OSS extension seam
tests/                    Frontend, CLI, and shared-package tests
```

## Development Notes

- Keep private agent and knowledge-service calls in server routes and server-only modules.
- Author shared contracts in `packages/shared/src/`, regenerate schemas with `pnpm gen:schema`, and keep the Pydantic mirror in `../backend/app/schemas/shared_models.py` aligned.
- UI translations currently live in `src/lib/i18n/messages/en.ts` and `vi.ts`.
- The root `pnpm dev` task starts the web package only; it does not launch the Python API or LiveKit worker.
