"""Persistence for Akasha report templates."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .db import get_connection

_COLUMNS = "id::text, name, columns, filters, sort, created_at, updated_at"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed
    return value if value is not None else fallback


def _row_to_template(row: tuple) -> dict[str, Any]:
    template_id, name, columns, filters, sort, created_at, updated_at = row
    return {
        "id": template_id,
        "name": name,
        "columns": _json(columns, []),
        "filters": _json(filters, {}),
        "sort": _json(sort, {}),
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def list_report_templates(team_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if team_id is not None:
        where = " WHERE team_id = %s"
        params.append(team_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM akasha.report_templates{where} ORDER BY created_at DESC",
            params,
        )
        return [_row_to_template(row) for row in cur.fetchall()]


def get_report_template(template_id: str, team_id: str | None = None) -> dict[str, Any] | None:
    params: list[Any] = [template_id]
    team_filter = ""
    if team_id is not None:
        team_filter = " AND team_id = %s"
        params.append(team_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM akasha.report_templates WHERE id = %s{team_filter}",
            params,
        )
        row = cur.fetchone()
        return _row_to_template(row) if row else None


def create_report_template(
    *,
    name: str,
    columns: list[str],
    filters: dict[str, Any],
    sort: dict[str, Any],
    owner_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO akasha.report_templates (name, columns, filters, sort, owner_id, team_id)
            VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
            RETURNING """ + _COLUMNS,
            (name, json.dumps(columns), json.dumps(filters), json.dumps(sort), owner_id, team_id),
        )
        return _row_to_template(cur.fetchone())


def update_report_template(
    template_id: str,
    *,
    name: str | None = None,
    columns: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    sort: dict[str, Any] | None = None,
    team_id: str | None = None,
) -> dict[str, Any] | None:
    set_clauses: list[str] = []
    params: list[Any] = []
    if name is not None:
        set_clauses.append("name = %s")
        params.append(name)
    if columns is not None:
        set_clauses.append("columns = %s::jsonb")
        params.append(json.dumps(columns))
    if filters is not None:
        set_clauses.append("filters = %s::jsonb")
        params.append(json.dumps(filters))
    if sort is not None:
        set_clauses.append("sort = %s::jsonb")
        params.append(json.dumps(sort))
    if not set_clauses:
        return get_report_template(template_id, team_id)
    params.append(template_id)
    team_filter = ""
    if team_id is not None:
        team_filter = " AND team_id = %s"
        params.append(team_id)
    sql = (
        "UPDATE akasha.report_templates SET "
        + ", ".join(set_clauses)
        + f" WHERE id = %s{team_filter} RETURNING {_COLUMNS}"
    )
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return _row_to_template(row) if row else None
