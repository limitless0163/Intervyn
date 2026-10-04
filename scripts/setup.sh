#!/usr/bin/env bash
set -euo pipefail

# Intervyn dev setup — installs JS + Python deps.
echo "Installing JS workspace deps (pnpm)…"
pnpm install

echo "Syncing Python agent deps (uv)…"
( cd backend && uv sync )

# Build BEFORE init: `pnpm intervyn` runs frontend/cli/dist/index.js, which only
# exists after `pnpm build` — on a fresh clone init-first fails.
echo "Done. Next: pnpm build && pnpm intervyn init && pnpm test (then: pnpm dev)"
