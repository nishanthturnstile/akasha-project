"""Persistence helpers for Phase 10 first-party operations modules."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from .db import get_connection


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _date(value: date | datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value if value is not None else fallback


def _attachment(row: tuple) -> dict[str, Any]:
    (
        attachment_id,
        parent_type,
        parent_id,
        filename,
        content_type,
        size_bytes,
        metadata,
        created_at,
        updated_at,
    ) = row
    return {
        "id": str(attachment_id),
        "parentType": parent_type,
        "parentId": str(parent_id) if parent_id else None,
        "filename": filename,
        "contentType": content_type,
        "sizeBytes": int(size_bytes) if size_bytes is not None else None,
        "metadata": _json(metadata, {}),
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def _activity(row: tuple, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    (
        activity_id,
        plot_id,
        field_name,
        legacy_group_name,
        crop_type,
        variety,
        season_label,
        activity_type,
        activity_date,
        assignee,
        status,
        input_product,
        cost,
        notes,
        group_names,
        metadata,
        created_at,
        updated_at,
    ) = row
    groups = [item for item in (group_names or []) if item]
    if not groups and legacy_group_name:
        groups = [legacy_group_name]
    return {
        "id": str(activity_id),
        "plotId": str(plot_id) if plot_id else None,
        "fieldName": field_name,
        "groupName": legacy_group_name,
        "groupNames": groups,
        "cropType": crop_type,
        "variety": variety,
        "seasonLabel": season_label,
        "activityType": activity_type,
        "activityDate": _date(activity_date),
        "assignee": assignee,
        "status": status,
        "inputProduct": input_product,
        "cost": float(cost) if cost is not None else None,
        "notes": notes,
        "attachments": attachments or [],
        "metadata": _json(metadata, {}),
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def _task(row: tuple, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    (
        task_id,
        plot_id,
        field_name,
        longitude,
        latitude,
        status,
        assignee,
        priority,
        notes,
        metadata,
        created_at,
        updated_at,
    ) = row
    return {
        "id": str(task_id),
        "plotId": str(plot_id) if plot_id else None,
        "fieldName": field_name,
        "longitude": longitude,
        "latitude": latitude,
        "status": status,
        "assignee": assignee,
        "priority": priority,
        "notes": notes,
        "attachments": attachments or [],
        "metadata": _json(metadata, {}),
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def _dataset(row: tuple) -> dict[str, Any]:
    (
        dataset_id,
        name,
        dataset_type,
        upload_status,
        original_filename,
        content_type,
        file_size_bytes,
        feature_count,
        validation_message,
        metadata,
        created_at,
        updated_at,
    ) = row
    return {
        "id": str(dataset_id),
        "name": name,
        "datasetType": dataset_type,
        "uploadStatus": upload_status,
        "originalFilename": original_filename,
        "contentType": content_type,
        "fileSizeBytes": int(file_size_bytes) if file_size_bytes is not None else None,
        "featureCount": feature_count,
        "validationMessage": validation_message,
        "metadata": _json(metadata, {}),
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


def _group(row: tuple, plot_ids: list[str] | None = None) -> dict[str, Any]:
    group_id, name, description, color, created_at, updated_at = row
    return {
        "id": str(group_id),
        "name": name,
        "description": description,
        "color": color,
        "plotIds": plot_ids or [],
        "createdAt": _iso(created_at),
        "updatedAt": _iso(updated_at),
    }


ATTACHMENT_COLUMNS = (
    "id::text, parent_type, parent_id::text, filename, content_type, size_bytes, "
    "metadata, created_at, updated_at"
)
ACTIVITY_COLUMNS = (
    "a.id::text, a.plot_id::text, p.name, p.group_name, p.crop_type, p.variety, "
    "p.season_label, a.activity_type, a.activity_date, a.assignee, a.status, "
    "a.input_product, a.cost, a.notes, "
    "COALESCE(array_agg(DISTINCT fg.name) FILTER (WHERE fg.name IS NOT NULL), '{}'), "
    "a.metadata, a.created_at, a.updated_at"
)
TASK_COLUMNS = (
    "t.id::text, t.plot_id::text, p.name, t.longitude, t.latitude, t.status, "
    "t.assignee, t.priority, t.notes, t.metadata, t.created_at, t.updated_at"
)
DATASET_COLUMNS = (
    "id::text, name, dataset_type, upload_status, original_filename, content_type, "
    "file_size_bytes, feature_count, validation_message, metadata, created_at, updated_at"
)
GROUP_COLUMNS = "id::text, name, description, color, created_at, updated_at"


def create_attachment(
    *,
    filename: str,
    content_type: str | None,
    size_bytes: int | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO akasha.attachments (
                filename, content_type, size_bytes, internal_storage_key, metadata
            )
            VALUES (%s, %s, %s, gen_random_uuid()::text, %s::jsonb)
            RETURNING {ATTACHMENT_COLUMNS}
            """,
            (filename, content_type, size_bytes, json.dumps(metadata or {})),
        )
        return _attachment(cur.fetchone())


def list_attachments(
    *,
    parent_type: str | None = None,
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if parent_type:
        clauses.append("parent_type = %s")
        params.append(parent_type)
    if parent_id:
        clauses.append("parent_id = %s")
        params.append(parent_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {ATTACHMENT_COLUMNS} FROM akasha.attachments{where} ORDER BY created_at DESC",
            params,
        )
        return [_attachment(row) for row in cur.fetchall()]


def _link_attachments(cur, attachment_ids: list[str], parent_type: str, parent_id: str) -> None:
    cur.execute(
        "UPDATE akasha.attachments SET parent_type = NULL, parent_id = NULL "
        "WHERE parent_type = %s AND parent_id = %s AND NOT (id = ANY(%s::uuid[]))",
        (parent_type, parent_id, attachment_ids),
    )
    for attachment_id in attachment_ids:
        cur.execute(
            "SELECT parent_type, parent_id::text FROM akasha.attachments WHERE id = %s",
            (attachment_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("ATTACHMENT_NOT_FOUND")
        existing_type, existing_parent = row
        if existing_type and (existing_type != parent_type or existing_parent != parent_id):
            raise ValueError("ATTACHMENT_ALREADY_LINKED")
        cur.execute(
            "UPDATE akasha.attachments SET parent_type = %s, parent_id = %s WHERE id = %s",
            (parent_type, parent_id, attachment_id),
        )


def _activity_by_id(cur, activity_id: str) -> dict[str, Any] | None:
    cur.execute(
        f"""
        SELECT {ACTIVITY_COLUMNS}
        FROM akasha.field_activities a
        LEFT JOIN akasha.plots p ON a.plot_id = p.id
        LEFT JOIN akasha.field_group_members fgm ON p.id = fgm.plot_id
        LEFT JOIN akasha.field_groups fg ON fgm.group_id = fg.id
        WHERE a.id = %s
        GROUP BY a.id, p.id
        """,
        (activity_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    cur.execute(
        f"SELECT {ATTACHMENT_COLUMNS} FROM akasha.attachments "
        "WHERE parent_type = 'activity' AND parent_id = %s",
        (activity_id,),
    )
    return _activity(row, [_attachment(item) for item in cur.fetchall()])


def create_activity(payload: dict[str, Any], attachment_ids: list[str]) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO akasha.field_activities (
                plot_id, activity_type, activity_date, assignee, status,
                input_product, cost, notes, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id::text
            """,
            (
                payload.get("plotId"),
                payload["activityType"],
                payload["activityDate"],
                payload.get("assignee"),
                payload.get("status", "planned"),
                payload.get("inputProduct"),
                payload.get("cost"),
                payload.get("notes"),
                json.dumps(payload.get("metadata") or {}),
            ),
        )
        activity_id = cur.fetchone()[0]
        _link_attachments(cur, attachment_ids, "activity", activity_id)
        return _activity_by_id(cur, activity_id)


def update_activity(
    activity_id: str,
    payload: dict[str, Any],
    attachment_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    column_by_field = {
        "plotId": "plot_id",
        "activityType": "activity_type",
        "activityDate": "activity_date",
        "assignee": "assignee",
        "status": "status",
        "inputProduct": "input_product",
        "cost": "cost",
        "notes": "notes",
    }
    set_clauses: list[str] = []
    params: list[Any] = []
    for field, column in column_by_field.items():
        if field in payload:
            set_clauses.append(f"{column} = %s")
            params.append(payload[field])
    if "metadata" in payload:
        set_clauses.append("metadata = %s::jsonb")
        params.append(json.dumps(payload.get("metadata") or {}))
    with get_connection() as conn, conn.cursor() as cur:
        if set_clauses:
            params.append(activity_id)
            cur.execute(
                "UPDATE akasha.field_activities SET "
                + ", ".join(set_clauses)
                + " WHERE id = %s RETURNING id::text",
                params,
            )
            if cur.fetchone() is None:
                return None
        elif _activity_by_id(cur, activity_id) is None:
            return None
        if attachment_ids is not None:
            _link_attachments(cur, attachment_ids, "activity", activity_id)
        return _activity_by_id(cur, activity_id)


def list_activities(filters: dict[str, Any]) -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {ACTIVITY_COLUMNS}
            FROM akasha.field_activities a
            LEFT JOIN akasha.plots p ON a.plot_id = p.id
            LEFT JOIN akasha.field_group_members fgm ON p.id = fgm.plot_id
            LEFT JOIN akasha.field_groups fg ON fgm.group_id = fg.id
            GROUP BY a.id, p.id
            ORDER BY a.activity_date DESC, a.created_at DESC
            """
        )
        rows = [_activity(row) for row in cur.fetchall()]
    return _filter_activities(rows, filters)


def _filter_activities(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    def ok(row: dict[str, Any]) -> bool:
        if filters.get("plotId") and row.get("plotId") != filters["plotId"]:
            return False
        if filters.get("groupName") and filters["groupName"] not in row.get("groupNames", []):
            return False
        for key, row_key in (
            ("cropType", "cropType"),
            ("variety", "variety"),
            ("activityType", "activityType"),
            ("assignee", "assignee"),
            ("status", "status"),
        ):
            if filters.get(key) and (
                str(row.get(row_key) or "").lower() != str(filters[key]).lower()
            ):
                return False
        if filters.get("year") and not str(row.get("activityDate") or "").startswith(
            str(filters["year"])
        ):
            return False
        return True

    return [row for row in rows if ok(row)]


def get_activity(activity_id: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        return _activity_by_id(cur, activity_id)


def delete_activity(activity_id: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE akasha.attachments SET parent_type = NULL, parent_id = NULL "
            "WHERE parent_type = 'activity' AND parent_id = %s",
            (activity_id,),
        )
        cur.execute("DELETE FROM akasha.field_activities WHERE id = %s", (activity_id,))
        return cur.rowcount > 0


def create_scout_task(payload: dict[str, Any], attachment_ids: list[str]) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO akasha.scout_tasks (
                plot_id, longitude, latitude, status, assignee, priority, notes, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id::text
            """,
            (
                payload.get("plotId"),
                payload.get("longitude"),
                payload.get("latitude"),
                payload.get("status", "new"),
                payload.get("assignee"),
                payload.get("priority", "medium"),
                payload.get("notes"),
                json.dumps(payload.get("metadata") or {}),
            ),
        )
        task_id = cur.fetchone()[0]
        _link_attachments(cur, attachment_ids, "scout_task", task_id)
        return _task_by_id(cur, task_id)


def update_scout_task(
    task_id: str,
    payload: dict[str, Any],
    attachment_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    column_by_field = {
        "plotId": "plot_id",
        "longitude": "longitude",
        "latitude": "latitude",
        "status": "status",
        "assignee": "assignee",
        "priority": "priority",
        "notes": "notes",
    }
    set_clauses: list[str] = []
    params: list[Any] = []
    for field, column in column_by_field.items():
        if field in payload:
            set_clauses.append(f"{column} = %s")
            params.append(payload[field])
    if "metadata" in payload:
        set_clauses.append("metadata = %s::jsonb")
        params.append(json.dumps(payload.get("metadata") or {}))
    with get_connection() as conn, conn.cursor() as cur:
        if set_clauses:
            params.append(task_id)
            cur.execute(
                "UPDATE akasha.scout_tasks SET "
                + ", ".join(set_clauses)
                + " WHERE id = %s RETURNING id::text",
                params,
            )
            if cur.fetchone() is None:
                return None
        elif _task_by_id(cur, task_id) is None:
            return None
        if attachment_ids is not None:
            _link_attachments(cur, attachment_ids, "scout_task", task_id)
        return _task_by_id(cur, task_id)


def _task_by_id(cur, task_id: str) -> dict[str, Any] | None:
    cur.execute(
        f"""
        SELECT {TASK_COLUMNS}
        FROM akasha.scout_tasks t
        LEFT JOIN akasha.plots p ON t.plot_id = p.id
        WHERE t.id = %s
        """,
        (task_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    cur.execute(
        f"SELECT {ATTACHMENT_COLUMNS} FROM akasha.attachments "
        "WHERE parent_type = 'scout_task' AND parent_id = %s",
        (task_id,),
    )
    return _task(row, [_attachment(item) for item in cur.fetchall()])


def list_scout_tasks(filters: dict[str, Any]) -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {TASK_COLUMNS}
            FROM akasha.scout_tasks t
            LEFT JOIN akasha.plots p ON t.plot_id = p.id
            ORDER BY t.created_at DESC
            """
        )
        rows = [_task(row) for row in cur.fetchall()]
    return [
        row for row in rows
        if (not filters.get("status") or row["status"] == filters["status"])
        and (not filters.get("plotId") or row.get("plotId") == filters["plotId"])
        and (
            not filters.get("search")
            or filters["search"].lower()
            in " ".join(
                str(row.get(k) or "") for k in ("fieldName", "notes", "assignee")
            ).lower()
        )
    ]


def get_scout_task(task_id: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        return _task_by_id(cur, task_id)


def delete_scout_task(task_id: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE akasha.attachments SET parent_type = NULL, parent_id = NULL "
            "WHERE parent_type = 'scout_task' AND parent_id = %s",
            (task_id,),
        )
        cur.execute("DELETE FROM akasha.scout_tasks WHERE id = %s", (task_id,))
        return cur.rowcount > 0


def create_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO akasha.uploaded_datasets (
                name, dataset_type, upload_status, original_filename, content_type,
                file_size_bytes, feature_count, validation_message,
                internal_storage_key, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, gen_random_uuid()::text, %s::jsonb)
            RETURNING {DATASET_COLUMNS}
            """,
            (
                payload["name"],
                payload["datasetType"],
                payload.get("uploadStatus", "uploaded"),
                payload.get("originalFilename"),
                payload.get("contentType"),
                payload.get("fileSizeBytes"),
                payload.get("featureCount"),
                payload.get("validationMessage"),
                json.dumps(payload.get("metadata") or {}),
            ),
        )
        return _dataset(cur.fetchone())


def list_datasets() -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {DATASET_COLUMNS} FROM akasha.uploaded_datasets ORDER BY created_at DESC"
        )
        return [_dataset(row) for row in cur.fetchall()]


def create_field_group(payload: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO akasha.field_groups (name, description, color)
            VALUES (%s, %s, %s)
            RETURNING {GROUP_COLUMNS}
            """,
            (payload["name"], payload.get("description"), payload.get("color")),
        )
        return _group(cur.fetchone())


def list_field_groups() -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {GROUP_COLUMNS} FROM akasha.field_groups ORDER BY name")
        groups = [_group(row) for row in cur.fetchall()]
        for group in groups:
            group["plotIds"] = group_plot_ids(cur, group["id"])
        return groups


def update_field_group(group_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    clauses: list[str] = []
    params: list[Any] = []
    for key, column in (("name", "name"), ("description", "description"), ("color", "color")):
        if key in payload:
            clauses.append(f"{column} = %s")
            params.append(payload[key])
    if not clauses:
        return get_field_group(group_id)
    params.append(group_id)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE akasha.field_groups SET "
            + ", ".join(clauses)
            + f" WHERE id = %s RETURNING {GROUP_COLUMNS}",
            params,
        )
        row = cur.fetchone()
        return _group(row, group_plot_ids(cur, group_id)) if row else None


def get_field_group(group_id: str) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {GROUP_COLUMNS} FROM akasha.field_groups WHERE id = %s", (group_id,))
        row = cur.fetchone()
        return _group(row, group_plot_ids(cur, group_id)) if row else None


def delete_field_group(group_id: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM akasha.field_groups WHERE id = %s", (group_id,))
        return cur.rowcount > 0


def assign_group_fields(group_id: str, plot_ids: list[str]) -> dict[str, Any] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {GROUP_COLUMNS} FROM akasha.field_groups WHERE id = %s", (group_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("DELETE FROM akasha.field_group_members WHERE group_id = %s", (group_id,))
        for plot_id in plot_ids:
            cur.execute(
                "INSERT INTO akasha.field_group_members (group_id, plot_id) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (group_id, plot_id),
            )
        return _group(row, group_plot_ids(cur, group_id))


def group_plot_ids(cur, group_id: str) -> list[str]:
    cur.execute(
        (
            "SELECT plot_id::text FROM akasha.field_group_members "
            "WHERE group_id = %s ORDER BY created_at"
        ),
        (group_id,),
    )
    return [row[0] for row in cur.fetchall()]
