# Akasha `web` gateway — the single public Railway service (Slice 0).
#
# Multi-stage build:
#   1) Build the Vite React SPA from apps/frontend (node:20-alpine).
#   2) Serve the static build + reverse-proxy /api and /tiles via Caddy.
#
# Build context MUST be the repository root so both apps/frontend and
# infra/gateway are available:
#   docker build -f infra/gateway/Dockerfile -t akasha-web .

# ---- Stage 1: build the SPA ------------------------------------------------
FROM node:20-alpine AS frontend-build
WORKDIR /build

# Install dependencies first for better layer caching.
COPY apps/frontend/package.json ./
# A committed yarn.lock is used when present (locked deps); otherwise resolved.
COPY apps/frontend/yarn.loc[k] ./
RUN yarn install --frozen-lockfile || yarn install

# Build the app.
COPY apps/frontend/ ./
RUN yarn build

# ---- Stage 2: Caddy gateway ------------------------------------------------
FROM caddy:2.8-alpine

COPY infra/gateway/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend-build /build/dist /srv

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:${PORT:-80}/health || exit 1

# The caddy base image's default entrypoint runs:
#   caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
