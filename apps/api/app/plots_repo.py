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
from datetime import UTC, date, datetime
from typing import Any

from .db import get_connection

# Column projection shared by every read (stable order for _row_to_plot).
_METADATA_COLUMN_BY_FIELD = {
    "groupName": "group_name",
    "cropType": "crop_type",
    "variety": "variety",
    "seasonLabel": "season_label",
    "sowingDate": "sowing_date",
    "plantingDate": "planting_date",
    "status": "status",
}
_METADATA_FIELDS = tuple(_METADATA_COLUMN_BY_FIELD)
_METADATA_COLUMNS = tuple(_METADATA_COLUMN_BY_FIELD.values())
_COLUMNS = "id::text, name, ST_AsGeoJSON(geometry), area_ha, created_at, updated_at, " + ", ".join(
    _METADATA_COLUMNS
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _date_iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _metadata_values(metadata: dict[str, Any] | None) -> list[Any]:
    metadata = metadata or {}
    return [metadata.get(field) for field in _METADATA_FIELDS]


def _row_to_plot(row: tuple) -> dict[str, Any]:
    (
        plot_id,
        name,
        geometry,
        area_ha,
        created_at,
        updated_at,
        group_name,
        crop_type,
        variety,
        season_label,
        sowing_date,
        planting_date,
        status,
    ) = row
    geom = json.loads(geometry) if isinstance(geometry, str) else geometry
    return {
        "id": plot_id,
        "name": name,
        "geometry": geom,
        "areaHa": round(float(area_ha), 4) if area_ha is not None else None,
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
        "groupName": group_name,
        "cropType": crop_type,
        "variety": variety,
        "seasonLabel": season_label,
        "sowingDate": _date_iso(sowing_date),
        "plantingDate": _date_iso(planting_date),
        "status": status,
    }


def _team_clause(team_id: str | None, params: list[Any]) -> str:
    if team_id is None:
        return ""
    params.append(team_id)
    return " WHERE team_id = %s"


def list_plots(team_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = _team_clause(team_id, params)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM akasha.plots{where} ORDER BY created_at DESC, id", params
        )
        return [_row_to_plot(r) for r in cur.fetchall()]


def get_plot(plot_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    params: list[Any] = [plot_id]
    team_filter = ""
    if team_id is not None:
        team_filter = " AND team_id = %s"
        params.append(team_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM akasha.plots WHERE id = %s{team_filter}", params)
        row = cur.fetchone()
        return _row_to_plot(row) if row else None


def create_plot(
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    metadata: dict[str, Any] | None = None,
    *,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        return _insert_plot(
            cur,
            name,
            geometry,
            area_ha,
            metadata,
            owner_id=owner_id,
            team_id=team_id,
        )


def _insert_plot(
    cur: Any,
    name: str,
    geometry: dict[str, Any],
    area_ha: float | None,
    metadata: dict[str, Any] | None = None,
    *,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    columns = ["name", "geometry", "area_ha", *_METADATA_COLUMNS]
    values_sql = ["%s", "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", "%s"]
    params: list[Any] = [name, json.dumps(geometry), area_ha, *_metadata_values(metadata)]
    values_sql.extend(["%s"] * len(_METADATA_COLUMNS))
    if owner_id is not None:
        columns.append("owner_id")
        values_sql.append("%s")
        params.append(owner_id)
    if team_id is not None:
        columns.append("team_id")
        values_sql.append("%s")
        params.append(team_id)
    sql = (
        f"INSERT INTO akasha.plots ({', '.join(columns)}) "
        f"VALUES ({', '.join(values_sql)}) "
        f"RETURNING {_COLUMNS}"
    )
    cur.execute(sql, params)
    return _row_to_plot(cur.fetchone())


def update_plot(
    plot_id: str,
    name: str | None = None,
    geometry: dict[str, Any] | None = None,
    area_ha: float | None = None,
    metadata: dict[str, Any] | None = None,
    team_id: str | None = None,
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
    for field, column in _METADATA_COLUMN_BY_FIELD.items():
        if metadata is not None and field in metadata:
            set_clauses.append(f"{column} = %s")
            params.append(metadata[field])
    if not set_clauses:
        # Caller guards NO_UPDATE_FIELDS; nothing to change -> return current row.
        return get_plot(plot_id, team_id)
    params.append(plot_id)
    team_filter = ""
    if team_id is not None:
        team_filter = " AND team_id = %s"
        params.append(team_id)
    sql = (
        "UPDATE akasha.plots SET "
        + ", ".join(set_clauses)
        + f" WHERE id = %s{team_filter} RETURNING {_COLUMNS}"
    )
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return _row_to_plot(row) if row else None


def delete_plot(plot_id: str, team_id: str | None = None) -> bool:
    params: list[Any] = [plot_id]
    team_filter = ""
    if team_id is not None:
        team_filter = " AND team_id = %s"
        params.append(team_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM akasha.plots WHERE id = %s{team_filter}", params)
        return cur.rowcount > 0


def create_plots_bulk(
    items: list[dict[str, Any]],
    *,
    owner_id: str | None = None,
    team_id: str | None = None,
) -> list[dict[str, Any]]:
    """Insert many plots in one transaction.

    Each item: {name, geometry, areaHa, metadata?}.
    """
    created: list[dict[str, Any]] = []
    with get_connection() as conn, conn.cursor() as cur:
        for item in items:
            created.append(
                _insert_plot(
                    cur,
                    item["name"],
                    item["geometry"],
                    item.get("areaHa"),
                    item.get("metadata"),
                    owner_id=owner_id,
                    team_id=team_id,
                )
            )
    return created
