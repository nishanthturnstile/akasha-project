"""Persistence for provider-backed zoning map public IDs."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .db import get_connection

_COLUMNS = (
    "id::text, plot_id::text, provider, external_zmap_id, provider_request_id, status, "
    "map_type, index_type, image_date, zone_count, min_zone_area_ha, metadata, "
    "created_at, updated_at"
)


def _date_iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _num(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def _row_to_zoning_map(row: tuple) -> dict[str, Any]:
    (
        map_id,
        plot_id,
        provider,
        external_zmap_id,
        provider_request_id,
        status,
        map_type,
        index_type,
        image_date,
        zone_count,
        min_zone_area_ha,
        metadata,
        created_at,
        updated_at,
    ) = row
    return {
        "id": map_id,
        "plotId": plot_id,
        "provider": provider,
        "externalZmapId": external_zmap_id,
        "providerRequestId": provider_request_id,
        "status": status,
        "mapType": map_type,
        "indexType": index_type,
        "imageDate": _date_iso(image_date),
        "zoneCount": zone_count,
        "minZoneAreaHa": _num(min_zone_area_ha),
        "metadata": _metadata(metadata),
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def create_zoning_map(
    *,
    plot_id: str,
    provider: str,
    status: str,
    map_type: str = "vegetation",
    external_zmap_id: str | None = None,
    provider_request_id: str | None = None,
    index_type: str | None = None,
    image_date: date | None = None,
    zone_count: int | None = None,
    min_zone_area_ha: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO akasha.zoning_maps (
                plot_id, provider, external_zmap_id, provider_request_id, status,
                map_type, index_type, image_date, zone_count, min_zone_area_ha, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (provider, external_zmap_id)
                WHERE external_zmap_id IS NOT NULL
            DO UPDATE SET
                plot_id = EXCLUDED.plot_id,
                provider_request_id = COALESCE(
                    EXCLUDED.provider_request_id,
                    akasha.zoning_maps.provider_request_id
                ),
                status = EXCLUDED.status,
                map_type = EXCLUDED.map_type,
                index_type = COALESCE(EXCLUDED.index_type, akasha.zoning_maps.index_type),
                image_date = COALESCE(EXCLUDED.image_date, akasha.zoning_maps.image_date),
                zone_count = COALESCE(EXCLUDED.zone_count, akasha.zoning_maps.zone_count),
                min_zone_area_ha = COALESCE(
                    EXCLUDED.min_zone_area_ha,
                    akasha.zoning_maps.min_zone_area_ha
                ),
                metadata = akasha.zoning_maps.metadata || EXCLUDED.metadata
            RETURNING """ + _COLUMNS,
            (
                plot_id,
                provider,
                external_zmap_id,
                provider_request_id,
                status,
                map_type,
                index_type,
                image_date,
                zone_count,
                min_zone_area_ha,
                json.dumps(metadata or {}),
            ),
        )
        return _row_to_zoning_map(cur.fetchone())


def list_zoning_maps(plot_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            (
                f"SELECT {_COLUMNS} FROM akasha.zoning_maps "
                "WHERE plot_id = %s ORDER BY created_at DESC"
            ),
            (plot_id,),
        )
        return [_row_to_zoning_map(row) for row in cur.fetchall()]


def get_zoning_map(plot_id: str, map_id: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM akasha.zoning_maps WHERE plot_id = %s AND id = %s",
            (plot_id, map_id),
        )
        row = cur.fetchone()
        return _row_to_zoning_map(row) if row else None


def update_zoning_map(
    plot_id: str,
    map_id: str,
    *,
    status: str | None = None,
    external_zmap_id: str | None = None,
    provider_request_id: str | None = None,
    index_type: str | None = None,
    zone_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    set_clauses: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("status", status),
        ("external_zmap_id", external_zmap_id),
        ("provider_request_id", provider_request_id),
        ("index_type", index_type),
        ("zone_count", zone_count),
    ):
        if value is not None:
            set_clauses.append(f"{column} = %s")
            params.append(value)
    if metadata is not None:
        set_clauses.append("metadata = metadata || %s::jsonb")
        params.append(json.dumps(metadata))
    if not set_clauses:
        return get_zoning_map(plot_id, map_id)
    params.extend([plot_id, map_id])
    sql = (
        "UPDATE akasha.zoning_maps SET "
        + ", ".join(set_clauses)
        + f" WHERE plot_id = %s AND id = %s RETURNING {_COLUMNS}"
    )
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return _row_to_zoning_map(row) if row else None
