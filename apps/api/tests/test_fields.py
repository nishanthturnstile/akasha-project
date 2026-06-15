"""Tests for Field CRUD + season linking.

No live PostGIS is required: `app.fields_repo` is monkeypatched with an
in-memory store so these tests exercise the full router/validation/serialization
path and the standard error shapes without a database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app import fields_repo
from app.auth import DEV_USER_ID
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

TEST_USER = DEV_USER_ID

VALID_POLY = {
    "type": "Polygon",
    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]],
}


class FakeSeasonStore:
    """Minimal in-memory stand-in for the PostGIS-backed fields_repo."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.seasons: dict[str, dict] = {}
        self._seq = 0

    def _now(self) -> str:
        return datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")

    def create_season(self, name: str, can_delete: bool = True) -> str:
        sid = str(uuid.uuid4())
        self.seasons[sid] = {"name": name, "can_delete": can_delete}
        return sid

    def create_field(
        self,
        user_id: str,
        name: str,
        geometry: dict,
        area_ha: float | None = None,
        group_id: str | None = None,
        season_ids: list[str] | None = None,
    ) -> dict:
        self._seq += 1
        fid = str(uuid.uuid4())
        sid_list = season_ids or []
        season_data = {
            sid: self.seasons.get(sid, {"name": "Unknown", "can_delete": False})
            for sid in sid_list
        }
        row = {
            "id": fid,
            "userId": user_id,
            "name": name,
            "areaHa": area_ha,
            "geometry": geometry,
            "groupId": group_id,
            "seasonIds": sid_list,
            "seasons": [
                {
                    "seasonId": sid,
                    "name": v["name"],
                    "canDelete": v["can_delete"],
                }
                for sid, v in season_data.items()
            ],
            "createdAt": self._now(),
            "updatedAt": self._now(),
            "_seq": self._seq,
        }
        self.rows[fid] = row
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def list_fields(self, user_id: str) -> list[dict]:
        ordered = sorted(self.rows.values(), key=lambda r: r["_seq"], reverse=True)
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in ordered if r["userId"] == user_id]

    def get_field(self, field_id: str, user_id: str) -> dict | None:
        row = self.rows.get(field_id)
        if row is None or row["userId"] != user_id:
            return None
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def update_field(self, field_id: str, user_id: str, **kwargs) -> dict | None:
        row = self.rows.get(field_id)
        if row is None or row["userId"] != user_id:
            return None
        if "name" in kwargs:
            row["name"] = kwargs["name"]
        if "geometry" in kwargs:
            row["geometry"] = kwargs["geometry"]
        if "area_ha" in kwargs:
            row["areaHa"] = kwargs["area_ha"]
        if "groupId" in kwargs:
            row["groupId"] = kwargs["groupId"]
        if "seasonIds" in kwargs:
            sid_list = kwargs["seasonIds"] or []
            season_data = {
                sid: self.seasons.get(sid, {"name": "Unknown", "can_delete": False})
                for sid in sid_list
            }
            row["seasonIds"] = sid_list
            row["seasons"] = [
                {
                    "seasonId": sid,
                    "name": v["name"],
                    "canDelete": v["can_delete"],
                }
                for sid, v in season_data.items()
            ]
        row["updatedAt"] = self._now()
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def delete_field(self, field_id: str, user_id: str) -> bool:
        row = self.rows.get(field_id)
        if row is None or row["userId"] != user_id:
            return False
        del self.rows[field_id]
        return True


@pytest.fixture
def store(monkeypatch):
    s = FakeSeasonStore()
    monkeypatch.setattr(fields_repo, "create_field", s.create_field)
    monkeypatch.setattr(fields_repo, "list_fields", s.list_fields)
    monkeypatch.setattr(fields_repo, "get_field", s.get_field)
    monkeypatch.setattr(fields_repo, "update_field", s.update_field)
    monkeypatch.setattr(fields_repo, "delete_field", s.delete_field)
    return s


# --------------------------------------------------------------------------
# 1) create returns 201 with seasons array
# --------------------------------------------------------------------------
def test_create_field_returns_201_with_seasons(store):
    sid = store.create_season("Kharif 2026", can_delete=True)
    r = client.post(
        "/api/fields",
        json={
            "name": "North field",
            "geometry": VALID_POLY,
            "seasonIds": [sid],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "North field"
    assert body["seasonIds"] == [sid]
    assert len(body["seasons"]) == 1
    assert body["seasons"][0]["seasonId"] == sid
    assert body["seasons"][0]["name"] == "Kharif 2026"
    assert body["seasons"][0]["canDelete"] is True


# --------------------------------------------------------------------------
# 2) list returns seasons array per field
# --------------------------------------------------------------------------
def test_list_fields_returns_seasons(store):
    sid1 = store.create_season("Kharif 2026", can_delete=True)
    sid2 = store.create_season("Rabi 2026", can_delete=False)
    store.create_field(TEST_USER, "Field A", VALID_POLY, season_ids=[sid1])
    store.create_field(TEST_USER, "Field B", VALID_POLY, season_ids=[sid1, sid2])

    r = client.get("/api/fields")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2

    # Ordered by creation desc (seq desc)
    field_b = body[0]
    assert field_b["name"] == "Field B"
    assert field_b["seasonIds"] == [sid1, sid2]
    assert len(field_b["seasons"]) == 2
    assert field_b["seasons"][0]["name"] == "Kharif 2026"
    assert field_b["seasons"][0]["canDelete"] is True
    assert field_b["seasons"][1]["name"] == "Rabi 2026"
    assert field_b["seasons"][1]["canDelete"] is False

    field_a = body[1]
    assert field_a["name"] == "Field A"
    assert field_a["seasonIds"] == [sid1]
    assert len(field_a["seasons"]) == 1


# --------------------------------------------------------------------------
# 3) get by id returns seasons array
# --------------------------------------------------------------------------
def test_get_field_by_id_returns_seasons(store):
    sid = store.create_season("Kharif 2026", can_delete=True)
    created = store.create_field(TEST_USER, "Field A", VALID_POLY, season_ids=[sid])
    fid = created["id"]

    r = client.get(f"/api/fields/{fid}")
    assert r.status_code == 200
    body = r.json()
    assert body["seasonIds"] == [sid]
    assert len(body["seasons"]) == 1
    assert body["seasons"][0]["seasonId"] == sid
    assert body["seasons"][0]["name"] == "Kharif 2026"
    assert body["seasons"][0]["canDelete"] is True


# --------------------------------------------------------------------------
# 4) update field updates seasons
# --------------------------------------------------------------------------
def test_update_field_updates_seasons(store):
    sid1 = store.create_season("Kharif 2026", can_delete=True)
    sid2 = store.create_season("Rabi 2026", can_delete=False)
    created = store.create_field(TEST_USER, "Field A", VALID_POLY, season_ids=[sid1])
    fid = created["id"]

    r = client.patch(
        f"/api/fields/{fid}",
        json={"seasonIds": [sid2]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["seasonIds"] == [sid2]
    assert len(body["seasons"]) == 1
    assert body["seasons"][0]["name"] == "Rabi 2026"
    assert body["seasons"][0]["canDelete"] is False


# --------------------------------------------------------------------------
# 5) field without seasons returns empty arrays
# --------------------------------------------------------------------------
def test_field_without_seasons_returns_empty(store):
    created = store.create_field(TEST_USER, "Bare field", VALID_POLY)
    fid = created["id"]

    r = client.get(f"/api/fields/{fid}")
    assert r.status_code == 200
    body = r.json()
    assert body["seasonIds"] == []
    assert body["seasons"] == []
