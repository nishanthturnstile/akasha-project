"""Slice 3 (Phase 3 — BFF API) tests for Plot CRUD + GeoJSON import/export.

No live PostGIS is required: `app.plots_repo` is monkeypatched with an in-memory
store, so these tests exercise the full router/validation/serialization path and
the standard error shapes without a database.
"""
import math
import uuid
from datetime import datetime, timezone

import pytest
from app import plots_repo
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

VALID_POLY = {
    "type": "Polygon",
    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]],
}
VALID_MULTIPOLY = {
    "type": "MultiPolygon",
    "coordinates": [[[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]]],
}
OVERSIZED_POLY = {
    "type": "Polygon",
    "coordinates": [[[78, 12], [79, 12], [79, 13], [78, 13], [78, 12]]],
}
POINT_GEOM = {"type": "Point", "coordinates": [78.2, 12.1]}


def _dense_polygon(n: int = 5002) -> dict:
    """A tiny but very high-vertex-count polygon (to trip TOO_MANY_VERTICES)."""
    cx, cy, r = 78.2, 12.1, 0.001
    ring = []
    for i in range(n - 1):
        ang = 2 * math.pi * i / (n - 1)
        ring.append([cx + r * math.cos(ang), cy + r * math.sin(ang)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


class FakeStore:
    """Minimal in-memory stand-in for the PostGIS-backed plots_repo."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self._seq = 0

    def _now(self) -> str:
        return datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    def create(self, name, geometry, area_ha):
        self._seq += 1
        pid = str(uuid.uuid4())
        row = {
            "id": pid,
            "name": name,
            "geometry": geometry,
            "areaHa": round(float(area_ha), 4) if area_ha is not None else None,
            "createdAt": self._now(),
            "updatedAt": self._now(),
            "_seq": self._seq,
        }
        self.rows[pid] = row
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def list(self):
        ordered = sorted(self.rows.values(), key=lambda r: r["_seq"], reverse=True)
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in ordered]

    def get(self, pid):
        row = self.rows.get(pid)
        return {k: v for k, v in row.items() if not k.startswith("_")} if row else None

    def update(self, pid, name=None, geometry=None, area_ha=None):
        row = self.rows.get(pid)
        if row is None:
            return None
        if name is not None:
            row["name"] = name
        if geometry is not None:
            row["geometry"] = geometry
            row["areaHa"] = round(float(area_ha), 4) if area_ha is not None else None
        row["updatedAt"] = self._now()
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def delete(self, pid):
        return self.rows.pop(pid, None) is not None

    def bulk(self, items):
        return [self.create(it["name"], it["geometry"], it.get("areaHa")) for it in items]


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(plots_repo, "list_plots", s.list)
    monkeypatch.setattr(plots_repo, "get_plot", s.get)
    monkeypatch.setattr(plots_repo, "create_plot", s.create)
    monkeypatch.setattr(plots_repo, "update_plot", s.update)
    monkeypatch.setattr(plots_repo, "delete_plot", s.delete)
    monkeypatch.setattr(plots_repo, "create_plots_bulk", s.bulk)
    return s


# --------------------------------------------------------------------------
# 1) create returns 201 typed payload
# --------------------------------------------------------------------------
def test_create_plot_returns_201_typed(store):
    r = client.post("/api/plots", json={"name": "  North field  ", "geometry": VALID_POLY})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "name", "geometry", "areaHa", "createdAt", "updatedAt"}
    assert body["name"] == "North field"  # trimmed
    assert body["geometry"]["type"] == "Polygon"
    assert isinstance(body["areaHa"], float) and 10 < body["areaHa"] < 50
    assert body["createdAt"].endswith("Z")


def test_create_plot_accepts_multipolygon(store):
    r = client.post("/api/plots", json={"name": "MP", "geometry": VALID_MULTIPOLY})
    assert r.status_code == 201
    assert r.json()["geometry"]["type"] == "MultiPolygon"


def test_create_plot_blank_name_400(store):
    r = client.post("/api/plots", json={"name": "   ", "geometry": VALID_POLY})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_NAME"


# --------------------------------------------------------------------------
# 2) list returns typed payloads (newest first)
# --------------------------------------------------------------------------
def test_list_plots_newest_first(store):
    client.post("/api/plots", json={"name": "first", "geometry": VALID_POLY})
    client.post("/api/plots", json={"name": "second", "geometry": VALID_POLY})
    r = client.get("/api/plots")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert names == ["second", "first"]


# --------------------------------------------------------------------------
# 3) get returns plot or 404 standard error
# --------------------------------------------------------------------------
def test_get_plot_found_and_404(store):
    created = client.post("/api/plots", json={"name": "p", "geometry": VALID_POLY}).json()
    ok = client.get(f"/api/plots/{created['id']}")
    assert ok.status_code == 200 and ok.json()["id"] == created["id"]

    missing = client.get(f"/api/plots/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_get_plot_invalid_uuid_is_404(store):
    r = client.get("/api/plots/not-a-uuid")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------
# 4) PATCH updates name and/or geometry
# --------------------------------------------------------------------------
def test_patch_updates_name_and_geometry(store):
    created = client.post("/api/plots", json={"name": "old", "geometry": VALID_POLY}).json()
    pid = created["id"]

    r1 = client.patch(f"/api/plots/{pid}", json={"name": "renamed"})
    assert r1.status_code == 200 and r1.json()["name"] == "renamed"

    r2 = client.patch(f"/api/plots/{pid}", json={"geometry": VALID_MULTIPOLY})
    assert r2.status_code == 200
    assert r2.json()["geometry"]["type"] == "MultiPolygon"
    assert isinstance(r2.json()["areaHa"], float)


def test_patch_missing_plot_404(store):
    r = client.patch(f"/api/plots/{uuid.uuid4()}", json={"name": "x"})
    assert r.status_code == 404


# --------------------------------------------------------------------------
# 5) PATCH with no fields -> 400 NO_UPDATE_FIELDS
# --------------------------------------------------------------------------
def test_patch_no_fields_400(store):
    created = client.post("/api/plots", json={"name": "p", "geometry": VALID_POLY}).json()
    r = client.patch(f"/api/plots/{created['id']}", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "NO_UPDATE_FIELDS"


# --------------------------------------------------------------------------
# 6) DELETE returns 204, missing returns 404
# --------------------------------------------------------------------------
def test_delete_204_then_404(store):
    created = client.post("/api/plots", json={"name": "p", "geometry": VALID_POLY}).json()
    pid = created["id"]
    r = client.delete(f"/api/plots/{pid}")
    assert r.status_code == 204
    assert r.content == b""
    assert client.delete(f"/api/plots/{pid}").status_code == 404


# --------------------------------------------------------------------------
# 7) invalid geometry -> 422 INVALID_GEOMETRY
# --------------------------------------------------------------------------
def test_create_invalid_geometry_422(store):
    r = client.post("/api/plots", json={"name": "p", "geometry": POINT_GEOM})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_GEOMETRY"


# --------------------------------------------------------------------------
# 8) oversized -> 413 POLYGON_TOO_LARGE
# --------------------------------------------------------------------------
def test_create_oversized_413(store):
    r = client.post("/api/plots", json={"name": "p", "geometry": OVERSIZED_POLY})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "POLYGON_TOO_LARGE"


# --------------------------------------------------------------------------
# 9) too many vertices -> 400 TOO_MANY_VERTICES
# --------------------------------------------------------------------------
def test_create_too_many_vertices_400(store):
    r = client.post("/api/plots", json={"name": "p", "geometry": _dense_polygon(5002)})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "TOO_MANY_VERTICES"


# --------------------------------------------------------------------------
# 10) import partial success: imported + rejected
# --------------------------------------------------------------------------
def test_import_geojson_partial_success(store):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "Good A"}, "geometry": VALID_POLY},
            {"type": "Feature", "properties": {}, "geometry": POINT_GEOM},        # invalid
            {"type": "Feature", "properties": {"title": "Good B"}, "geometry": VALID_MULTIPOLY},
        ],
    }
    r = client.post("/api/plots/import/geojson", json=fc)
    assert r.status_code == 200
    body = r.json()
    assert body["importedCount"] == 2
    assert body["rejectedCount"] == 1
    assert {p["name"] for p in body["imported"]} == {"Good A", "Good B"}
    rej = body["rejected"][0]
    assert rej["index"] == 1 and rej["code"] == "INVALID_GEOMETRY"


def test_import_raw_geometry_and_default_name(store):
    r = client.post("/api/plots/import/geojson", json=VALID_POLY)
    assert r.status_code == 200
    body = r.json()
    assert body["importedCount"] == 1
    assert body["imported"][0]["name"] == "Imported plot 1"


def test_import_too_many_features_400(store):
    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": VALID_POLY}] * 501,
    }
    r = client.post("/api/plots/import/geojson", json=fc)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "TOO_MANY_FEATURES"


def test_import_unsupported_type_400(store):
    r = client.post("/api/plots/import/geojson", json={"type": "Nonsense"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_GEOJSON"


# --------------------------------------------------------------------------
# 11) export.geojson media type is application/geo+json
# --------------------------------------------------------------------------
def test_export_single_plot_media_type(store):
    created = client.post("/api/plots", json={"name": "p", "geometry": VALID_POLY}).json()
    r = client.get(f"/api/plots/{created['id']}/export.geojson")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/geo+json")
    feat = r.json()
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Polygon"
    assert feat["properties"]["name"] == "p"


def test_export_all_plots_feature_collection(store):
    client.post("/api/plots", json={"name": "a", "geometry": VALID_POLY})
    client.post("/api/plots", json={"name": "b", "geometry": VALID_MULTIPOLY})
    r = client.get("/api/plots/export.geojson")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/geo+json")
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2


# --------------------------------------------------------------------------
# 12) security: responses never leak secrets / internals / SQL / stack traces
# --------------------------------------------------------------------------
def test_no_secret_or_internal_leakage_in_503(monkeypatch):
    # Simulate a DB driver failure whose message embeds a DSN-like secret.
    secret_dsn = "postgresql://akasha:s3cr3t@postgis.railway.internal:5432/akasha"

    def boom():
        raise RuntimeError(f"connection failed: {secret_dsn}")

    monkeypatch.setattr(plots_repo, "list_plots", boom)
    r = client.get("/api/plots")
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "PLOTS_BACKEND_UNAVAILABLE"
    text = r.text
    for leak in ["postgresql://", "s3cr3t", "railway.internal", "Traceback", "RuntimeError"]:
        assert leak not in text, f"leaked '{leak}' in 503 body"


def test_no_internal_leakage_in_success_paths(store, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://akasha:s3cr3t@db:5432/akasha")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "minio-secret-XYZ")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    created = client.post("/api/plots", json={"name": "p", "geometry": VALID_POLY})
    listing = client.get("/api/plots")
    export = client.get(f"/api/plots/{created.json()['id']}/export.geojson")
    blob = created.text + listing.text + export.text
    for leak in [
        "s3cr3t", "minio-secret-XYZ", "http://minio:9000", "DATABASE_URL",
        "AWS_SECRET_ACCESS_KEY", "Traceback", "psycopg", "INSERT INTO", "SELECT ",
    ]:
        assert leak not in blob, f"leaked '{leak}' in response body"
