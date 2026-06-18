"""Selected-field native export route tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.config import settings
from app.main import app
from app.routers import analytics_router as field_analytics
from app.routers import field_exports_router as field_exports
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def native_settings(monkeypatch):
    monkeypatch.setattr(settings, "default_source_id", "resourcesat-2a-liss3-boa")


def _plot(**overrides: Any) -> dict[str, Any]:
    plot = {
        "id": "plot-1",
        "name": "North Field",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]],
        },
        "areaHa": 5.0,
    }
    plot.update(overrides)
    return plot


def _stats_response(
    index_type: str = "NDVI",
    acquisition_date: str = "2026-06-01",
) -> dict[str, Any]:
    return {
        "indexType": index_type,
        "sourceId": "resourcesat-2a-liss3-boa",
        "acquisitionDate": acquisition_date,
        "statistics": {
            "min": 0.1,
            "max": 0.8,
            "mean": 0.55,
            "stddev": 0.12,
            "validPixelPercent": 82.5,
            "cloudMaskedPercent": 10.0,
            "coveragePercent": 92.5,
        },
        "pixelCounts": {
            "totalPixels": 100,
            "nodataPixels": 7,
            "coveragePixels": 93,
            "maskedPixels": 10,
            "validPixels": 83,
        },
        "metadata": {"formula": "(NIR - RED) / (NIR + RED)", "bands": ["BAND4", "BAND3"]},
    }


def test_index_csv_export_uses_server_side_geometry_and_cloud_mapping(monkeypatch):
    monkeypatch.setattr(field_exports.fields_repo, "get_field", lambda *_: _plot())
    calls: list[dict[str, Any]] = []

    def fake_compute_statistics(**kwargs):
        calls.append(kwargs)
        return _stats_response(
            index_type=kwargs["index_type"],
            acquisition_date=kwargs["acquisition_date"],
        )

    monkeypatch.setattr(field_analytics, "compute_statistics", fake_compute_statistics)
    r = client.get(
        "/api/fields/plot-1/exports/index"
        "?format=csv&sourceId=resourcesat-2a-liss3-boa&acquisitionDate=2026-06-01"
        "&indexType=NDVI&clouds=true&cloudShadows=false&cirrus=false"
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "North-Field_2026-06-01_NDVI.csv" in r.headers["content-disposition"]
    assert "mean" in r.text
    assert "0.55" in r.text
    assert calls[0]["source_id"] == "resourcesat-2a-liss3-boa"
    assert calls[0]["excluded_mask_classes"] == (0, 2)
    assert "masked_pixels" in r.text
    assert "scl_excluded_pixels" not in r.text


def test_index_geojson_export_contains_safe_field_statistics(monkeypatch):
    monkeypatch.setattr(field_exports.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **kwargs: _stats_response(
            index_type=kwargs["index_type"],
            acquisition_date=kwargs["acquisition_date"],
        ),
    )

    r = client.get(
        "/api/fields/plot-1/exports/index"
        "?format=geojson&acquisitionDate=2026-06-01&indexType=NDVI"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "Feature"
    assert body["properties"]["mean"] == pytest.approx(0.55)
    assert body["properties"]["cloudMaskMapping"]["nativeExcludedMaskClasses"] == [0, 2, 3]
    assert body["properties"]["cloudMaskMapping"]["warnings"]


@pytest.mark.parametrize("export_format", ["shp", "geotiff"])
def test_provider_backed_export_formats_are_unavailable(monkeypatch, export_format):
    monkeypatch.setattr(field_exports.fields_repo, "get_field", lambda *_: _plot())
    r = client.get(
        "/api/fields/plot-1/exports/index"
        f"?format={export_format}&acquisitionDate=2026-06-01&indexType=NDVI"
    )
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "EXPORT_FORMAT_UNAVAILABLE"
    assert "Traceback" not in r.text


def test_report_csv_export_uses_native_trend_points(monkeypatch):
    monkeypatch.setattr(field_exports.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "list_dates",
        lambda _: [{"acquisitionDate": "2026-06-01"}],
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **kwargs: _stats_response(
            index_type=kwargs["index_type"],
            acquisition_date=kwargs["acquisition_date"],
        ),
    )

    r = client.get(
        "/api/fields/plot-1/exports/report.csv"
        "?indexType=NDVI&startDate=2026-06-01&endDate=2026-06-30"
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "North-Field_NDVI_analytics.csv" in r.headers["content-disposition"]
    assert "acquisition_date" in r.text
    assert "2026-06-01" in r.text
    for leak in ["s3://", "minio", "postgres", "Traceback"]:
        assert leak not in r.text


def test_index_export_missing_date_and_field_are_sanitized(monkeypatch):
    monkeypatch.setattr(field_exports.fields_repo, "get_field", lambda *_: None)
    missing = client.get("/api/fields/missing/exports/index?format=csv&acquisitionDate=2026-06-01")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "FIELD_NOT_FOUND"

    monkeypatch.setattr(field_exports.fields_repo, "get_field", lambda *_: _plot())
    no_date = client.get("/api/fields/plot-1/exports/index?format=csv")
    assert no_date.status_code == 400
    assert no_date.json()["error"]["code"] == "MISSING_DATE"
