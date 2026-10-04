#!/usr/bin/env bash
set -euo pipefail

# Intervyn dev setup — installs JS + Python deps.
echo "Installing JS workspace deps (pnpm)…"
pnpm --dir frontend install --frozen-lockfile

echo "Syncing Python agent deps (uv)…"
( cd backend && uv sync )

# Build BEFORE init: `pnpm --dir frontend intervyn` runs frontend/cli/dist/index.js, which only
# exists after `pnpm --dir frontend build` — on a fresh clone init-first fails.
echo "Done. Next: pnpm --dir frontend build && pnpm --dir frontend intervyn init && pnpm --dir frontend test (then: pnpm --dir frontend dev)"
