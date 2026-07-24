from __future__ import annotations

from app.discovery_normalization import natural_sort_key, normalize_search_text
from app.main import app
from app.models import ScoutTask
from app.repositories import field_discovery_repo
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

client = TestClient(app)
SEASON_ID = "10000000-0000-4000-8000-000000000001"
FIELD_ID = "20000000-0000-4000-8000-000000000001"


def _field() -> dict:
    return {
        "id": FIELD_ID,
        "name": "Café Field 10",
        "areaHa": 2.3456,
        "crop": {"id": 1, "name": "Rice"},
        "group": None,
        "district": "Mysuru",
        "country": "India",
        "createdAt": "2026-07-01T00:00:00Z",
        "updatedAt": "2026-07-02T00:00:00Z",
        "focusBounds": {"west": 170, "south": -2, "east": 190, "north": 2},
    }


def _filters(status: str | None = None) -> dict:
    return {
        "seasonId": SEASON_ID,
        "q": "cafe",
        "cropIds": [1],
        "groupIds": [],
        "includeUngrouped": True,
        "sort": "name_asc",
        "status": status,
    }


def test_unicode_and_natural_normalization() -> None:
    assert normalize_search_text("  CAFÉ\tField  ") == "cafe field"
    assert natural_sort_key("Field 2") < natural_sort_key("Field 10")
    assert natural_sort_key("Árbol 02") == natural_sort_key("arbol 2")


def test_scout_search_includes_visible_field_snapshot() -> None:
    filters = {
        "status": "new",
        "q": "  CAFÉ  Field ",
        "cropIds": [],
        "groupIds": [],
        "includeUngrouped": False,
    }
    statement = field_discovery_repo._apply_task_filters(select(ScoutTask), filters)
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "fields.name_search_key" in sql
    assert "scout_tasks.field_name_snapshot" in sql
    assert "cafe field" in sql


def test_scout_name_sort_uses_visible_snapshot_when_field_is_unavailable() -> None:
    order = field_discovery_repo._task_order("name_asc")
    sql = str(
        select(ScoutTask).order_by(*order).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "coalesce(akasha.fields.name_sort_key" in sql
    assert "scout_tasks.field_name_snapshot" in sql


def test_field_discovery_contract_is_geometry_light_and_repeats_filters(monkeypatch) -> None:
    captured: dict = {}

    def fake_list_fields(**kwargs):
        captured.update(kwargs)
        return {
            "items": [_field()],
            "pinnedItems": [_field()],
            "appliedFilters": _filters(),
            "page": 1,
            "pageSize": 20,
            "total": 1,
            "totalPages": 1,
            "resultBounds": _field()["focusBounds"],
        }

    monkeypatch.setattr(field_discovery_repo, "list_fields", fake_list_fields)
    response = client.get(
        "/api/field-discovery/fields",
        params=[
            ("seasonId", SEASON_ID),
            ("q", "café"),
            ("cropId", "1"),
            ("cropId", "999"),
            ("groupId", "invalid"),
            ("includeUngrouped", "true"),
            ("pinnedFieldIds", FIELD_ID),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["focusBounds"]["east"] == 190
    assert "geometry" not in body["items"][0]
    assert captured["crop_ids"] == [1, 999]
    assert captured["group_ids"] == ["invalid"]
    assert captured["pinned_field_ids"] == [FIELD_ID]


def test_scout_snapshot_disables_find_field(monkeypatch) -> None:
    monkeypatch.setattr(
        field_discovery_repo,
        "list_scout_tasks",
        lambda **_: {
            "items": [
                {
                    "id": "30000000-0000-4000-8000-000000000001",
                    "status": "new",
                    "priority": "high",
                    "notes": "Inspect",
                    "field": None,
                    "fieldNameSnapshot": "Deleted field",
                    "findFieldAvailable": False,
                }
            ],
            "pinnedItems": [],
            "appliedFilters": _filters("new"),
            "page": 1,
            "pageSize": 20,
            "total": 1,
            "totalPages": 1,
            "resultBounds": None,
        },
    )
    response = client.get(
        "/api/field-discovery/scout-tasks",
        params={"seasonId": SEASON_ID, "status": "new"},
    )
    assert response.status_code == 200
    task = response.json()["items"][0]
    assert task["fieldNameSnapshot"] == "Deleted field"
    assert task["findFieldAvailable"] is False


def test_facets_and_map_contracts(monkeypatch) -> None:
    monkeypatch.setattr(
        field_discovery_repo,
        "get_facets",
        lambda **_: {
            "crops": [{"id": 1, "name": "Rice"}],
            "groups": [{"id": FIELD_ID, "name": "North"}],
            "hasUngrouped": True,
        },
    )
    monkeypatch.setattr(
        field_discovery_repo,
        "get_map_features",
        lambda **_: {
            "fields": {"type": "FeatureCollection", "features": []},
            "taskPoints": {"type": "FeatureCollection", "features": []},
        },
    )
    facets = client.get(
        "/api/field-discovery/facets",
        params={"seasonId": SEASON_ID, "target": "monitoring"},
    )
    assert facets.status_code == 200
    assert facets.json()["hasUngrouped"] is True
    map_response = client.get(
        "/api/field-discovery/map",
        params={
            "seasonId": SEASON_ID,
            "target": "monitoring",
            "west": 170,
            "south": -10,
            "east": 190,
            "north": 10,
            "zoom": 8,
        },
    )
    assert map_response.status_code == 200
    assert map_response.json()["fields"]["type"] == "FeatureCollection"
