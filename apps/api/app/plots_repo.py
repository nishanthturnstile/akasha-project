"""Plot persistence (Slice 3) — raw SQL over PostGIS via synchronous psycopg.

Rules (engineering-dos-donts.md / phase-3 prompt):
  * Raw SQL with parameter binding ONLY — never string-format user input.
  * `psycopg` is imported lazily (via app.db.get_connection) so importing the
    FastAPI app never requires a DB driver.
  * Geometry is written with ST_SetSRID(ST_GeomFromGeoJSON(...), 4326) and read
    back with ST_AsGeoJSON(...), returning parsed GeoJSON objects (not strings).
  * Rows are normalized to the frontend contract (camelCase, ISO-8601 'Z').
  * These functions are synchronous/blocking; callers MUST run them off the
    event loop (anyio.to_thread.run_sync).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import get_connection

# Column projection shared by every read (stable order for _row_to_plot).
_COLUMNS = (
    "id::text, name, ST_AsGeoJSON(geometry), area_ha, created_at, updated_at"
)
_INSERT_RETURNING = (
    "INSERT INTO akasha.plots (name, geometry, area_ha) "
    "VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s) "
    f"RETURNING {_COLUMNS}"
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_to_plot(row: tuple) -> dict[str, Any]:
    plot_id, name, geometry, area_ha, created_at, updated_at = row
    geom = json.loads(geometry) if isinstance(geometry, str) else geometry
    return {
        "id": plot_id,
        "name": name,
        "geometry": geom,
        "areaHa": round(float(area_ha), 4) if area_ha is not None else None,
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def list_plots() -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM akasha.plots ORDER BY created_at DESC, id")
        return [_row_to_plot(r) for r in cur.fetchall()]


def get_plot(plot_id: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM akasha.plots WHERE id = %s", (plot_id,))
        row = cur.fetchone()
        return _row_to_plot(row) if row else None


def create_plot(name: str, geometry: dict[str, Any], area_ha: float | None) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(_INSERT_RETURNING, (name, json.dumps(geometry), area_ha))
        return _row_to_plot(cur.fetchone())


def update_plot(
    plot_id: str,
    name: str | None = None,
    geometry: dict[str, Any] | None = None,
    area_ha: float | None = None,
) -> dict[str, Any] | None:
    # Column names are fixed literals; only values are parameter-bound.
    set_clauses: list[str] = []
    params: list[Any] = []
    if name is not None:
        set_clauses.append("name = %s")
        params.append(name)
    if geometry is not None:
        set_clauses.append("geometry = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)")
        params.append(json.dumps(geometry))
        set_clauses.append("area_ha = %s")
        params.append(area_ha)
    if not set_clauses:
        # Caller guards NO_UPDATE_FIELDS; nothing to change -> return current row.
        return get_plot(plot_id)
    params.append(plot_id)
    sql = (
        "UPDATE akasha.plots SET "
        + ", ".join(set_clauses)
        + f" WHERE id = %s RETURNING {_COLUMNS}"
    )
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return _row_to_plot(row) if row else None


def delete_plot(plot_id: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM akasha.plots WHERE id = %s", (plot_id,))
        return cur.rowcount > 0


def create_plots_bulk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert many plots in one transaction. Each item: {name, geometry, areaHa}."""
    created: list[dict[str, Any]] = []
    with get_connection() as conn, conn.cursor() as cur:
        for item in items:
            cur.execute(
                _INSERT_RETURNING,
                (item["name"], json.dumps(item["geometry"]), item.get("areaHa")),
            )
            created.append(_row_to_plot(cur.fetchone()))
    return created
