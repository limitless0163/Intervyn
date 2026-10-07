# Intervyn web (Next.js 16, App Router) — production image (WP-12).
#
# Multi-stage, Next.js *standalone* output (see frontend/next.config.ts:
# `output: 'standalone'`). The final image is a slim `node server.js` with no
# install step at runtime.
#
# BUILD CONTEXT = frontend (the complete pnpm workspace lives here).
# Build from the repository root:
#
#     docker build -f frontend/Dockerfile -t intervyn-web frontend
#
# docker-compose.yml uses the deps stage below for the local dev server.
# Direct builds use the final runner stage for production.

# ---- deps: install the full workspace (need every member's manifest) --------
FROM node:22-slim AS deps
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable
WORKDIR /repo/frontend

# Copy lockfile + workspace config + every package manifest first for caching.
# pnpm needs ALL workspace members' package.json to resolve the lockfile.
COPY pnpm-lock.yaml pnpm-workspace.yaml .npmrc package.json ./
COPY packages/shared/package.json packages/shared/package.json
COPY packages/ee/package.json packages/ee/package.json
COPY packages/agent/package.json packages/agent/package.json
COPY cli/package.json cli/package.json
# Optional native downloads can fail without failing pnpm's install. Verify
# SWC here so a broken image cannot start Next and hang on its first request.
RUN pnpm install --frozen-lockfile \
 && node -e "const { createRequire } = require('node:module'); const requireNext = createRequire(require.resolve('next/package.json')); requireNext('@next/swc-linux-' + process.arch + '-gnu');"

# ---- builder: build @intervyn/shared then the web app ------------------
FROM node:22-slim AS builder
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /repo/frontend

# NEXT_PUBLIC_* vars are inlined into the browser bundle at BUILD time by
# Next.js — values injected at runtime (compose env_file) never reach client
# code. Accept them as build args here and export them as env so `pnpm build`
# bakes them in. Pass them with `docker build --build-arg` when building the
# production image. Hosted-only billing vars
# (NEXT_PUBLIC_PADDLE_*) are intentionally not plumbed — the OSS compose
# path runs without billing.
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_SENTRY_DSN
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN

# Bring in installed node_modules, then the full source tree.
COPY --from=deps /repo/frontend ./
COPY . .

# Some Next projects expect public to exist; guarantee it so the
# runner COPY below never fails even when there are no static assets yet.
RUN mkdir -p public

# Build workspace packages before the root Next.js app.
RUN pnpm build

# ---- runner: slim standalone server ----------------------------------------
FROM node:22-slim AS runner
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
WORKDIR /app

# Run as a non-root user.
RUN groupadd --system --gid 1001 nodejs \
 && useradd --system --uid 1001 --gid nodejs nextjs

# The workspace root is also the app root, so server.js is at the bundle root.
COPY --from=builder --chown=nextjs:nodejs /repo/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/frontend/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/frontend/public ./public

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
