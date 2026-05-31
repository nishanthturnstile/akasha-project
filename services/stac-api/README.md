# `services/stac-api` — STAC API (stac-fastapi-pgstac)

Serves STAC collections/items, date/source discovery, and asset metadata. The
BFF reads this catalog; it does **not** duplicate STAC metadata into app tables.
**Private service.**

- Image: `ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2`.
- Internal port: `8080`. Health: `GET /_mgmt/ping`.
- Database: pgSTAC inside the `postgis` service (vars use the real
  `POSTGRES_HOST_READER/WRITER/PORT/USER/PASS/DBNAME` names).

> pgSTAC schema + the Sentinel-2 collection seed are added in **Slice 1**.
> Slice 0 provides only the pinned image + connection contract.
