# Frontend agent guide

See the [repository guide](../AGENTS.md) for workspace setup, service topology, workspace commands, shared-contract policy, environment handling, and CI. This file covers `frontend/`, including its workspace packages and CLI.

## Stack and source layout

- Next.js 16 App Router, React 19, TypeScript 5.9, Tailwind CSS 4, and Vitest. TypeScript extends `./tsconfig.base.json`; `@/*` resolves to `src/*`.
- `src/app/` owns pages, layouts, Server Actions, and API route handlers. `src/components/` is grouped by feature; `features/`, `hooks/`, `lib/`, `services/`, `constants/`, `styles/`, `types/`, and `utils/` contain supporting code.
- `packages/shared/src/` is the Zod contract source and exports built ESM/CJS. `packages/shared/schema/` is generated. `packages/ee/src/` is the open-core seam; its OSS feature flags are false and `gateRequest` allows requests.
- `cli/src/` implements the `intervyn` CLI. `cli/avatars.manifest.json` is the avatar manifest; pulled avatar files are written under ignored `frontend/public/avatars/`.

## Commands and tests

Run from `frontend/` (or add `--dir frontend` when running pnpm from the repository root):

- Web: `pnpm --filter @intervyn/web dev`, `pnpm build`, `pnpm typecheck:web`, `pnpm test:web`.
- Shared contracts: `pnpm --filter @intervyn/shared gen:schema`, `pnpm --filter @intervyn/shared typecheck`, `pnpm --filter @intervyn/shared test`.
- CLI: `pnpm --filter @intervyn/cli build`, `pnpm --filter @intervyn/cli typecheck`, `pnpm --filter @intervyn/cli test`.
- `pnpm build`, `pnpm typecheck`, and `pnpm test` run Turbo package tasks followed by the root web app task. The root app must not be registered as a Turbo task using these same scripts, which would recurse.
- `pnpm intervyn …` changes to the repository root and executes the built `frontend/cli/dist/index.js`; run `pnpm build` first on a fresh checkout.

Vitest runs in the Node environment. Web tests are under `frontend/tests/`; the shared and CLI Vitest configs point to `frontend/tests/shared/` and `frontend/tests/cli/`. `pnpm test` runs all Turbo workspace test tasks. Follow the existing test placement and config rather than assuming a browser/React Testing Library setup.

## Contracts and integration boundaries

- Define or change shared API/wire types in `packages/shared/src/`, export them through `src/index.ts` as needed, then run `pnpm gen:schema`. Never edit generated JSON Schema files by hand. Keep the matching Pydantic mirror in `../backend/app/schemas/shared_models.py` aligned; read the backend guide for parity rules.
- Keep internal agent calls in server code (`src/services/api.ts` and server route handlers). `src/lib/env.ts` separates browser-safe `publicEnv` from `serverEnv`; never import server secrets into a Client Component. Public `NEXT_PUBLIC_*` references must stay statically named so Next can inline them.
- The `src/proxy.ts` matcher refreshes Supabase sessions for page requests and deliberately excludes several API routes. API handlers perform their own input validation, auth/distribution checks, upstream error handling, and response behavior; preserve those boundaries when adding endpoints.
- `LIVEKIT_AGENT_NAME` must match the worker dispatch name. The token's explicit dispatch is required for the LiveKit worker to join.
- Supabase is optional in the OSS build. Preserve null-safe behavior when browser/server Supabase clients are unconfigured. `@intervyn/ee` is intentionally inert upstream; do not add hosted-only auth, billing, or premium behavior to its OSS stub.
- User-facing translations are in `src/lib/i18n/messages/en.ts` and `zh.ts`; when changing an existing translated string, keep both locale maps in sync. English is the default UI locale, with Simplified Chinese as the only alternate UI locale.

## Style, configuration, and builds

- Follow strict TypeScript settings in `./tsconfig.base.json` and the existing component/server boundaries. Use `cn` from `src/utils/cn.ts` for class merging where the surrounding code does.
- `.editorconfig` sets two-space indentation for TypeScript/Markdown and LF endings. `pnpm lint` checks the frontend paths listed in `frontend/package.json`; it is Prettier checking, not a separate ESLint script. `pnpm format` writes those same configured paths.
- Use `.env.example` for env names. Production `NEXT_PUBLIC_*` values are build-time client config; `frontend/Dockerfile` receives them as build args and uses Next standalone output. The single local Compose configuration uses the Dockerfile's `deps` stage and runs Next's dev server, which reads public config at runtime. Server-only values such as `SUPABASE_SERVICE_ROLE_KEY`, `INTERNAL_API_SECRET`, LiveKit secrets, and R2 credentials must remain server-side.
- The Docker build context for `frontend/Dockerfile` is `frontend/`, which contains the complete pnpm workspace. Preserve that workspace build path and `next.config.ts`'s `transpilePackages`/standalone settings.
