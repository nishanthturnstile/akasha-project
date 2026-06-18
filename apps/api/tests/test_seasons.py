"""Season API regression tests for router/schema extraction.

No live PostGIS is required: `app.repositories.seasons_repo` is monkeypatched
with an in-memory store so these tests exercise request aliases, validation,
serialization, and standard Akasha error shapes.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.auth import DEV_USER_ID
from app.main import app
from app.raster.errors import AkashaError
from app.repositories import seasons_repo
from fastapi.testclient import TestClient

client = TestClient(app)

TEST_USER = DEV_USER_ID


class FakeSeasonStore:
    """Minimal in-memory stand-in for the PostGIS-backed seasons_repo."""

    def __init__(self):
        self.rows: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def _now(self) -> str:
        return datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if not key.startswith("_")}

    def create_season(
        self,
        user_id: str,
        name: str,
        start_date,
        end_date,
        can_delete: bool | None = None,
        field_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._seq += 1
        season_id = str(uuid.uuid4())
        row = {
            "id": season_id,
            "userId": user_id,
            "name": name,
            "startDate": start_date.isoformat() if start_date else None,
            "endDate": end_date.isoformat() if end_date else None,
            "canDelete": can_delete if can_delete is not None else self._seq > 1,
            "totalArea": 0.0,
            "fieldIds": [
                {"id": field_id, "name": f"Field {idx + 1}", "canRemove": True, "isMapped": True}
                for idx, field_id in enumerate(field_ids or [])
            ],
            "createdAt": self._now(),
            "updatedAt": self._now(),
            "_seq": self._seq,
        }
        self.rows[season_id] = row
        return self._public(row)

    def list_seasons(self, user_id: str) -> list[dict[str, Any]]:
        return [self._public(row) for row in self.rows.values() if row["userId"] == user_id]

    def get_season(self, season_id: str, user_id: str) -> dict[str, Any] | None:
        row = self.rows.get(season_id)
        if row is None or row["userId"] != user_id:
            return None
        return self._public(row)

    def update_season(self, season_id: str, user_id: str, **kwargs: Any) -> dict[str, Any] | None:
        row = self.rows.get(season_id)
        if row is None or row["userId"] != user_id:
            return None
        if "name" in kwargs:
            row["name"] = kwargs["name"]
        if "start_date" in kwargs:
            value = kwargs["start_date"]
            row["startDate"] = value.isoformat() if value else None
        if "end_date" in kwargs:
            value = kwargs["end_date"]
            row["endDate"] = value.isoformat() if value else None
        if "fieldIds" in kwargs:
            row["fieldIds"] = [
                {"id": field_id, "name": f"Field {idx + 1}", "canRemove": True, "isMapped": True}
                for idx, field_id in enumerate(kwargs["fieldIds"] or [])
            ]
        row["updatedAt"] = self._now()
        return self._public(row)

    def delete_season(self, season_id: str, user_id: str) -> bool:
        row = self.rows.get(season_id)
        if row is None or row["userId"] != user_id:
            return False
        del self.rows[season_id]
        return True


@pytest.fixture
def store(monkeypatch):
    fake = FakeSeasonStore()
    monkeypatch.setattr(seasons_repo, "create_season", fake.create_season)
    monkeypatch.setattr(seasons_repo, "list_seasons", fake.list_seasons)
    monkeypatch.setattr(seasons_repo, "get_season", fake.get_season)
    monkeypatch.setattr(seasons_repo, "update_season", fake.update_season)
    monkeypatch.setattr(seasons_repo, "delete_season", fake.delete_season)
    return fake


def test_create_season_accepts_field_ids_alias(store):
    field_id = str(uuid.uuid4())

    response = client.post(
        "/api/seasons",
        json={
            "name": "Kharif 2026",
            "startDate": "2026-06-01",
            "endDate": "2026-10-15",
            "fieldIds": [field_id],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Kharif 2026"
    assert body["startDate"] == "2026-06-01"
    assert body["endDate"] == "2026-10-15"
    assert body["fieldIds"] == [{"id": field_id, "name": "Field 1", "canRemove": True, "isMapped": True}]


def test_update_season_accepts_field_ids_alias(store):
    old_field_id = str(uuid.uuid4())
    new_field_id = str(uuid.uuid4())
    created = store.create_season(TEST_USER, "Kharif 2026", None, None, field_ids=[old_field_id])

    response = client.patch(
        f"/api/seasons/{created['id']}",
        json={"fieldIds": [new_field_id]},
    )

    assert response.status_code == 200
    assert response.json()["fieldIds"] == [
        {"id": new_field_id, "name": "Field 1", "canRemove": True, "isMapped": True}
    ]


def test_update_season_updates_date_aliases(store):
    created = store.create_season(TEST_USER, "Kharif 2026", None, None)

    response = client.patch(
        f"/api/seasons/{created['id']}",
        json={"startDate": "2026-06-01", "endDate": "2026-10-15"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["startDate"] == "2026-06-01"
    assert body["endDate"] == "2026-10-15"


def test_update_season_empty_patch_returns_standard_error(store):
    created = store.create_season(TEST_USER, "Kharif 2026", None, None)

    response = client.patch(f"/api/seasons/{created['id']}", json={})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "NO_UPDATE_FIELDS"
    assert "Traceback" not in response.text


@pytest.mark.parametrize("name", ["   ", "x" * 101])
def test_invalid_season_name_uses_standard_error_shape(store, name):
    response = client.post("/api/seasons", json={"name": name})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]
    assert "Traceback" not in response.text


def test_invalid_season_date_range_uses_standard_error_shape(store):
    response = client.post(
        "/api/seasons",
        json={"name": "Kharif 2026", "startDate": "2026-10-15", "endDate": "2026-06-01"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]
    assert "Traceback" not in response.text


def test_delete_last_season_raises_controlled_akasha_error(monkeypatch):
    user_uuid = uuid.UUID(TEST_USER)
    season_id = str(uuid.uuid4())

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def count(self) -> int:
            return 1

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return SimpleNamespace(user_id=user_uuid)

        def query(self, *_args, **_kwargs):
            return FakeQuery()

    @contextmanager
    def fake_session_scope():
        yield FakeSession()

    monkeypatch.setattr(seasons_repo, "session_scope", fake_session_scope)

    with pytest.raises(AkashaError) as exc_info:
        seasons_repo.delete_season(season_id, TEST_USER)

    assert exc_info.value.code == "CANNOT_DELETE_SEASON"
    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {"seasonId": season_id}
