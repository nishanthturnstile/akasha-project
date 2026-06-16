# `infra/gateway` — Akasha web gateway (Caddy)

The **only public service**. It is built as a single container that bundles the
static React SPA (built from `apps/frontend`) and a Caddy reverse proxy.

## Routes

| Route | Behaviour |
|---|---|
| `GET /health` | Returns `200 ok` (container/Compose health check). |
| `/api/*` | Reverse-proxied to the `api` service (path preserved). |
| `/tiles/*` | Reverse-proxied to the `titiler` service (native rewrite in Slice 2). |
| `/*` | Static SPA with history-API fallback to `index.html`. |

## Build

Build context is the **repository root** (needs `apps/frontend` + `infra/gateway`):

```bash
docker build -f infra/gateway/Dockerfile -t akasha-web .
docker run -p 8080:80 -e API_UPSTREAM_URL=http://host.docker.internal:8000 akasha-web
# GET http://localhost:8080/health -> ok
```

For self-hosted Coolify/Azure deployment, the `web` service uses build context
= repository root (Dockerfile path `infra/gateway/Dockerfile`, healthcheck
`/health`). See [`infra/selfhosted/README.md`](../selfhosted/README.md).

## Security guardrails

- Only this service is publicly reachable. Never expose `api`, `titiler`,
  `stac-api`, `postgis`, or `minio` publicly.
- `GATEWAY_BASIC_AUTH` (empty = off) is the Wave 1 shared-secret gate.
