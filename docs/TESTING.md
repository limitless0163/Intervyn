# Testing

Cross-cutting / end-to-end tests that span multiple packages (e.g. web ⇄ agent contract
round-trips, full-stack smoke tests). Unit tests are grouped by responsibility:

- `frontend/tests/shared` (vitest — TS contracts)
- `frontend/tests/*.test.ts` (vitest — web lib/utils)
- `frontend/tests/cli` (vitest — CLI utilities)
- `backend/tests` (pytest — prep/live/post, mock adapters)
- `backend/tests/lightrag` (pytest — naive RAG backend)

System-level / E2E tests will live under the root `tests/` directory when
implemented; that directory is not created as a placeholder.

Run `pnpm test` for the workspace suites. To check only one frontend workspace,
use `pnpm --filter @deepinterview/web test`,
`pnpm --filter @deepinterview/cli test`, or
`pnpm --filter @deepinterview/shared test`.
The backend suite lives in `backend/tests`; the independent LightRAG project
also runs its suite with `uv --directory backend/services/lightrag run pytest`.
