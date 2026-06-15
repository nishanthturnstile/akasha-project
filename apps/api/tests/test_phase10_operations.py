"""Phase 10 operations/scout/data-manager/field-groups route tests."""
from __future__ import annotations

from typing import Any

from app.routers import data_manager_router as data_manager, field_group_router as field_groups, operation_router as operations, scout_task_router as scout_tasks
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

ATTACHMENT_ID = "11111111-1111-4111-8111-111111111111"
ACTIVITY_ID = "22222222-2222-4222-8222-222222222222"
TASK_ID = "33333333-3333-4333-8333-333333333333"
GROUP_ID = "44444444-4444-4444-8444-444444444444"
DATASET_ID = "55555555-5555-4555-8555-555555555555"


def _attachment(**overrides: Any) -> dict[str, Any]:
    item = {
        "id": ATTACHMENT_ID,
        "parentType": None,
        "parentId": None,
        "filename": "photo.jpg",
        "contentType": "image/jpeg",
        "sizeBytes": 12,
        "metadata": {},
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
        "internalStorageKey": "s3://should-not-leak",
    }
    item.update(overrides)
    item.pop("internalStorageKey", None)
    return item


def _activity(**overrides: Any) -> dict[str, Any]:
    item = {
        "id": ACTIVITY_ID,
        "plotId": "plot-1",
        "fieldName": "North Field",
        "groupNames": ["North"],
        "cropType": "Paddy",
        "variety": "Sona",
        "activityType": "fertilizer",
        "activityDate": "2026-06-04",
        "assignee": "=Mallory",
        "status": "planned",
        "inputProduct": "+NPK",
        "cost": 12.5,
        "notes": "@note\r\nwith newline",
        "attachments": [_attachment(parentType="activity", parentId=ACTIVITY_ID)],
        "metadata": {},
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
    }
    item.update(overrides)
    return item


def _task(**overrides: Any) -> dict[str, Any]:
    item = {
        "id": TASK_ID,
        "plotId": "plot-1",
        "fieldName": "North Field",
        "longitude": 77.1,
        "latitude": 12.1,
        "status": "new",
        "assignee": "Scout",
        "priority": "high",
        "notes": "Check canopy",
        "attachments": [_attachment(parentType="scout_task", parentId=TASK_ID)],
        "metadata": {},
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
    }
    item.update(overrides)
    return item


def _assert_no_leaks(text: str) -> None:
    for leaked in ["internalStorageKey", "storage_key", "s3://", "minio", "Traceback", "SELECT "]:
        assert leaked not in text


def test_attachment_metadata_and_activity_export_are_sanitized(monkeypatch):
    monkeypatch.setattr(operations.phase10_repo, "create_attachment", lambda **_: _attachment())
    monkeypatch.setattr(operations.phase10_repo, "list_attachments", lambda **_: [_attachment()])
    monkeypatch.setattr(operations.phase10_repo, "create_activity", lambda *_: _activity())
    monkeypatch.setattr(
        operations.phase10_repo,
        "update_activity",
        lambda *_: _activity(status="done", attachments=[]),
    )
    monkeypatch.setattr(operations.phase10_repo, "list_activities", lambda *_: [_activity()])

    created = client.post(
        "/api/attachments",
        json={"filename": "photo.jpg", "contentType": "image/jpeg", "sizeBytes": 12},
    )
    assert created.status_code == 201
    _assert_no_leaks(created.text)

    activity = client.post(
        "/api/fields/plot-1/activities",
        json={
            "activityType": "fertilizer",
            "activityDate": "2026-06-04",
            "attachmentIds": [ATTACHMENT_ID],
        },
    )
    assert activity.status_code == 201
    assert activity.json()["attachments"][0]["id"] == ATTACHMENT_ID
    _assert_no_leaks(activity.text)

    updated = client.patch(
        f"/api/activities/{ACTIVITY_ID}",
        json={"status": "done", "attachmentIds": []},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"
    assert updated.json()["attachments"] == []

    exported = client.get("/api/activities/export.csv?year=2026")
    assert exported.status_code == 200
    assert "'=Mallory" in exported.text
    assert "'+NPK" in exported.text
    assert "'@note  with newline" in exported.text
    _assert_no_leaks(exported.text)


def test_scout_task_coordinates_and_attachment_listing(monkeypatch):
    monkeypatch.setattr(scout_tasks.phase10_repo, "create_scout_task", lambda *_: _task())
    monkeypatch.setattr(
        scout_tasks.phase10_repo,
        "update_scout_task",
        lambda *_: _task(status="closed"),
    )
    monkeypatch.setattr(scout_tasks.phase10_repo, "list_scout_tasks", lambda *_: [_task()])
    monkeypatch.setattr(operations.phase10_repo, "list_attachments", lambda **_: [_attachment()])

    bad = client.post("/api/scout-tasks", json={"longitude": 181, "latitude": 12})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_COORDINATES"

    created = client.post(
        "/api/scout-tasks",
        json={
            "plotId": "plot-1",
            "longitude": 77.1,
            "latitude": 12.1,
            "attachmentIds": [ATTACHMENT_ID],
        },
    )
    assert created.status_code == 201
    assert created.json()["attachments"][0]["parentType"] == "scout_task"
    _assert_no_leaks(created.text)

    closed = client.patch(f"/api/scout-tasks/{TASK_ID}", json={"status": "closed"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    monkeypatch.setattr(
        scout_tasks.phase10_repo,
        "create_scout_task",
        lambda *_: (_ for _ in ()).throw(ValueError("ATTACHMENT_NOT_FOUND")),
    )
    missing_attachment = client.post("/api/scout-tasks", json={"attachmentIds": [ATTACHMENT_ID]})
    assert missing_attachment.status_code == 404
    assert missing_attachment.json()["error"]["code"] == "ATTACHMENT_NOT_FOUND"

    attachments = client.get(f"/api/attachments?parentType=scout_task&parentId={TASK_ID}")
    assert attachments.status_code == 200
    _assert_no_leaks(attachments.text)


def test_data_manager_metadata_upload_and_connection_placeholder(monkeypatch):
    dataset = {
        "id": DATASET_ID,
        "name": "fields.geojson",
        "datasetType": "geojson",
        "uploadStatus": "parsed",
        "originalFilename": "fields.geojson",
        "contentType": "application/geo+json",
        "fileSizeBytes": 45,
        "featureCount": 1,
        "metadata": {},
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
        "internalStorageKey": "s3://should-not-leak",
    }
    dataset.pop("internalStorageKey")
    monkeypatch.setattr(data_manager.phase10_repo, "create_dataset", lambda _payload: dataset)
    monkeypatch.setattr(data_manager.phase10_repo, "list_datasets", lambda: [dataset])

    uploaded = client.post(
        "/api/datasets/upload",
        files={"file": ("fields.geojson", b'{"type":"FeatureCollection","features":[{}]}')},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["featureCount"] == 1
    _assert_no_leaks(uploaded.text)

    monkeypatch.setattr(data_manager, "MAX_UPLOAD_BYTES", 8)
    oversized = client.post(
        "/api/datasets/upload",
        files={"file": ("big.geojson", b"x" * 16)},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "DATASET_UPLOAD_TOO_LARGE"

    connection = client.get("/api/connections/john-deere")
    assert connection.status_code == 200
    assert connection.json()["status"] == "not_connected"


def test_field_group_crud_and_assignment(monkeypatch):
    group = {
        "id": GROUP_ID,
        "name": "North Block",
        "description": "Demo group",
        "color": "#22c55e",
        "plotIds": ["plot-1"],
        "createdAt": "2026-06-04T00:00:00Z",
        "updatedAt": "2026-06-04T00:00:00Z",
    }
    monkeypatch.setattr(field_groups.phase10_repo, "create_field_group", lambda _payload: group)
    monkeypatch.setattr(field_groups.phase10_repo, "list_field_groups", lambda *_: [group])
    monkeypatch.setattr(field_groups.phase10_repo, "update_field_group", lambda *_: group)
    monkeypatch.setattr(field_groups.phase10_repo, "delete_field_group", lambda *_: True)
    monkeypatch.setattr(field_groups.phase10_repo, "assign_group_fields", lambda *_: group)

    created = client.post("/api/field-groups", json={"name": "North Block"})
    assert created.status_code == 201
    assert created.json()["name"] == "North Block"

    listed = client.get("/api/field-groups")
    assert listed.status_code == 200
    assert listed.json()[0]["plotIds"] == ["plot-1"]

    assigned = client.post(f"/api/field-groups/{GROUP_ID}/fields", json={"plotIds": ["plot-1"]})
    assert assigned.status_code == 200
    assert assigned.json()["plotIds"] == ["plot-1"]
