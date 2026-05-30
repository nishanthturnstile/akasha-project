# `apps/frontend` — Akasha frontend (Vite + React + TypeScript)

Slice 0 **skeleton** of the deployable frontend. It renders a placeholder
landing page and proves the same-origin `/api/*` contract by reading the BFF
skeleton service registry.

> The interactive product UX — MapLibre GL JS map, Terra Draw plot drawing,
> layer panel, and index panel — is delivered in **Slices 4&ndash;5** and is
> intentionally **not** implemented here.

## Develop

```bash
cd apps/frontend
yarn install
yarn dev      # http://localhost:5173 (proxies /api and /tiles to :8000)
```

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
