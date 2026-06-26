# `apps/frontend` — Akasha frontend (Vite + React + TypeScript)

Slice 0 **skeleton** of the deployable frontend. It renders a placeholder
landing page and proves the same-origin `/api/*` contract by reading the BFF
skeleton service registry.

> The interactive product UX — MapLibre GL JS map, Terra Draw plot drawing,
> layer panel, and index panel — is delivered in **Slices 4&ndash;5** and is
> intentionally **not** implemented here.

## Develop with the Docker backend

Use the repository-level local-dev launcher from the repo root. It starts the
Docker backend/gateway stack, prepares the database/catalog, and then starts
this Vite app locally with hot reload:

```bash
make dev
```

If `make` is unavailable:

```bash
bash scripts/dev-local.sh
```

Vite serves the frontend on `FRONTEND_PORT` from `infra/docker/.env`
(`5173` by default) and proxies `/api/*` and `/tiles/*` to the Docker gateway.
If that port is already in use, the launcher updates `FRONTEND_PORT` to the
next free port and prints the actual URL.

The gateway port is read from `infra/docker/.env` (`WEB_PORT`, default `8080`).
If that port is already occupied by another process, the launcher updates
`WEB_PORT` to the next free port before starting Docker. Custom local port
pairs therefore work without manually setting `AKASHA_DEV_PROXY_TARGET`.

## Develop this package only

Use this only after the Docker backend/gateway is already running:

```bash
cd apps/frontend
npx --yes yarn install --frozen-lockfile
npx --yes yarn dev      # http://localhost:<FRONTEND_PORT from infra/docker/.env>
```

Set `AKASHA_DEV_PROXY_TARGET` only when you intentionally want to override the
gateway URL.

## Build

```bash
yarn build    # -> dist/  (served by the web gateway in production)
```

## Production

The production artifact is built into the `web` gateway container
(`infra/gateway/Dockerfile`). The standalone `Dockerfile` here is optional and
used only for previewing the frontend in isolation.

## Rules (engineering-dos-donts.md)

- Never fetch COGs directly from the browser.
- Never hard-code MinIO object URLs or COG paths.
- Use API-provided source/date/tile metadata; call only same-origin `/api/*`
  and `/tiles/*`.
