"""Tests for the LISS-4 best-resolution resolver and provenance in analytics responses.

Covers TEST-006 (resolver unit tests) and TEST-007 (stats/overlay/point response
provenance fields and headers; trend metadata annotation).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from app.config import settings
from app.main import app
from app.raster import catalog_resolver as catalog
from app.raster.catalog_resolver import (
    RESOURCESAT_LISS3_SOURCE_ID,
    RESOURCESAT_LISS4_SOURCE_ID,
    ResolutionResult,
    resolve_best_resolution_source,
)
from app.routers import analytics_router as field_analytics
from fastapi.testclient import TestClient

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FIELD_POLY = {
    "type": "Polygon",
    "coordinates": [
        [[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]
    ],
}

_LISS4_BOUNDS_COVERING = [78.0, 12.0, 79.0, 13.0]
_LISS4_BOUNDS_NOT_COVERING = [80.0, 13.0, 81.0, 14.0]


def _liss4_date(acq_date: str, bounds: list[float] | None = None) -> dict[str, Any]:
    return {
        "acquisitionDate": acq_date,
        "bounds": bounds or _LISS4_BOUNDS_COVERING,
        "tileAvailable": True,
    }


def _plot(**overrides: Any) -> dict[str, Any]:
    plot: dict[str, Any] = {
        "id": "field-1",
        "name": "Test Field",
        "geometry": _FIELD_POLY,
        "areaHa": 5.0,
    }
    plot.update(overrides)
    return plot


def _stats_response(
    source_id: str = RESOURCESAT_LISS3_SOURCE_ID,
    index_type: str = "NDVI",
    acquisition_date: str = "2026-01-15",
) -> dict[str, Any]:
    return {
        "indexType": index_type,
        "sourceId": source_id,
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
        "metadata": {
            "formula": "(NIR - RED) / (NIR + RED)",
            "bands": ["BAND4", "BAND3"],
            "itemId": f"item-{acquisition_date}",
            "warnings": [],
        },
    }


def _liss4_assets() -> list[dict[str, Any]]:
    return [
        {
            "analyticHref": "s3://akasha-cogs/liss4/analytic.tif",
            "maskHref": "s3://akasha-cogs/liss4/mask.tif",
            "bandNames": ["BAND2", "BAND3", "BAND4"],
            "bandRoleMapping": {"GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4"},
            "scale": 0.0001,
            "offset": 0.0,
            "excludedMaskClasses": [0, 2, 3],
            "nodataPolicy": "mask_only",
            "bbox": _LISS4_BOUNDS_COVERING,
        }
    ]


@pytest.fixture(autouse=True)
def _auth_disabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)


# ---------------------------------------------------------------------------
# TEST-006 — resolver unit tests
# ---------------------------------------------------------------------------


def test_resolver_prefers_liss4_when_composite_in_window(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: (
            [_liss4_date("2026-01-15")]
            if source_id == RESOURCESAT_LISS4_SOURCE_ID
            else []
        ),
    )
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
        window_days=12,
    )
    assert result.enhanced is True
    assert result.source_id == RESOURCESAT_LISS4_SOURCE_ID
    assert result.basis_date == "2026-01-15"
    assert result.resolution_meters == pytest.approx(5.8)
    assert result.provenance_note is None


def test_resolver_picks_closest_liss4_date_within_window(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: (
            [_liss4_date("2026-01-12"), _liss4_date("2026-01-08")]
            if source_id == RESOURCESAT_LISS4_SOURCE_ID
            else []
        ),
    )
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
        window_days=12,
    )
    assert result.enhanced is True
    # 2026-01-12 is 3 days away; 2026-01-08 is 7 days away → 12 chosen.
    assert result.basis_date == "2026-01-12"


def test_resolver_falls_back_when_no_liss4_in_window(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: (
            [_liss4_date("2026-02-01")]  # 17 days away, outside window_days=12
            if source_id == RESOURCESAT_LISS4_SOURCE_ID
            else []
        ),
    )
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
        window_days=12,
    )
    assert result.enhanced is False
    assert result.source_id == RESOURCESAT_LISS3_SOURCE_ID
    assert result.provenance_note is None


def test_resolver_falls_back_when_liss4_bbox_does_not_cover_field(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: (
            [_liss4_date("2026-01-15", bounds=_LISS4_BOUNDS_NOT_COVERING)]
            if source_id == RESOURCESAT_LISS4_SOURCE_ID
            else []
        ),
    )
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
        window_days=12,
    )
    assert result.enhanced is False
    assert result.source_id == RESOURCESAT_LISS3_SOURCE_ID


def test_resolver_ndmi_always_returns_primary():
    # NDMI must always use LISS-3 regardless of prefer_high_res.
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDMI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
    )
    assert result.enhanced is False
    assert result.source_id == RESOURCESAT_LISS3_SOURCE_ID
    assert result.provenance_note is not None


def test_resolver_ndmi_provenance_note_mentions_liss3_and_swir():
    """TASK-D06: NDMI provenance note must name LISS-3 and explain no SWIR."""
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDMI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
    )
    note = result.provenance_note or ""
    assert "LISS-3" in note
    assert "SWIR" in note


def test_resolver_ndre_always_returns_primary():
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDRE",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
    )
    assert result.enhanced is False
    assert result.source_id == RESOURCESAT_LISS3_SOURCE_ID


def test_resolver_prefer_high_res_false_skips_liss4_catalog_lookup(monkeypatch):
    calls: list[str] = []

    def spy(source_id: str) -> list:
        calls.append(source_id)
        return []

    monkeypatch.setattr(catalog, "list_dates", spy)
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=False,
        window_days=12,
    )
    assert result.enhanced is False
    assert result.source_id == RESOURCESAT_LISS3_SOURCE_ID
    # list_dates must NOT be called for LISS-4 when prefer_high_res=False.
    assert RESOURCESAT_LISS4_SOURCE_ID not in calls


def test_resolver_catalog_error_falls_back_to_primary_silently(monkeypatch):
    def boom(_source_id: str) -> list:
        raise RuntimeError("Simulated catalog failure")

    monkeypatch.setattr(catalog, "list_dates", boom)
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
        window_days=12,
    )
    assert result.enhanced is False
    assert result.source_id == RESOURCESAT_LISS3_SOURCE_ID
    assert result.provenance_note is None


def test_resolver_result_is_resolution_result_dataclass():
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDMI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
    )
    assert isinstance(result, ResolutionResult)


def test_resolver_non_liss3_primary_is_not_enhanced(monkeypatch):
    """Issue 1: LISS-4 enhancement must be skipped for non-LISS3 primary sources."""
    calls: list[str] = []

    def spy(source_id: str) -> list:
        calls.append(source_id)
        return [_liss4_date("2026-01-15")]

    monkeypatch.setattr(catalog, "list_dates", spy)
    for non_liss3 in ("sentinel-2-l2a", "resourcesat-2a-awifs-boa"):
        result = resolve_best_resolution_source(
            primary_source_id=non_liss3,
            index_type="NDVI",
            field_geometry=_FIELD_POLY,
            acquisition_date="2026-01-15",
            prefer_high_res=True,
            window_days=12,
        )
        assert result.enhanced is False, f"Enhanced must be False for primary={non_liss3}"
        assert result.source_id == non_liss3
        assert result.provenance_note is None
    # list_dates must NOT have been called for LISS-4 for any non-LISS3 primary.
    assert RESOURCESAT_LISS4_SOURCE_ID not in calls


def test_resolver_ndvi_fallback_has_no_provenance_note(monkeypatch):
    """Issue 2: ordinary no-LISS4-date fallback must not set a provenance note."""
    monkeypatch.setattr(
        catalog,
        "list_dates",
        lambda source_id: (
            [_liss4_date("2026-02-15")]  # outside 12-day window
            if source_id == RESOURCESAT_LISS4_SOURCE_ID
            else []
        ),
    )
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDVI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
        window_days=12,
    )
    assert result.enhanced is False
    assert result.provenance_note is None


def test_resolver_ndmi_provenance_note_exact_text():
    """Issue 2: NDMI provenance note must contain the canonical SWIR explanation."""
    result = resolve_best_resolution_source(
        primary_source_id=RESOURCESAT_LISS3_SOURCE_ID,
        index_type="NDMI",
        field_geometry=_FIELD_POLY,
        acquisition_date="2026-01-15",
        prefer_high_res=True,
    )
    assert result.provenance_note == (
        "Moisture served from LISS-3 (24 m) -- LISS-4 has no SWIR band."
    )


def test_bbox_from_geometry_handles_multipolygon():
    """Issue 3: _bbox_from_geometry must handle MultiPolygon geometry."""
    from app.raster.catalog_resolver import _bbox_from_geometry

    multi = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[78.0, 12.0], [78.1, 12.0], [78.1, 12.1], [78.0, 12.0]]],
            [[[79.0, 13.0], [79.2, 13.0], [79.2, 13.2], [79.0, 13.0]]],
        ],
    }
    bbox = _bbox_from_geometry(multi)
    assert bbox is not None
    minx, miny, maxx, maxy = bbox
    assert minx == pytest.approx(78.0)
    assert miny == pytest.approx(12.0)
    assert maxx == pytest.approx(79.2)
    assert maxy == pytest.approx(13.2)


# ---------------------------------------------------------------------------
# TEST-007 — response provenance: statistics endpoint
# ---------------------------------------------------------------------------


def _fake_resolution(enhanced: bool = False, basis_date: str | None = None) -> ResolutionResult:
    if enhanced:
        return ResolutionResult(
            source_id=RESOURCESAT_LISS4_SOURCE_ID,
            resolution_meters=5.8,
            enhanced=True,
            basis_date=basis_date or "2026-01-13",
            provenance_note=None,
        )
    return ResolutionResult(
        source_id=RESOURCESAT_LISS3_SOURCE_ID,
        resolution_meters=24.0,
        enhanced=False,
        basis_date=None,
        provenance_note=None,
    )


def test_statistics_response_includes_provenance_fields_when_enhanced(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **_kw: _fake_resolution(enhanced=True, basis_date="2026-01-13"),
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: _stats_response(
            source_id=RESOURCESAT_LISS4_SOURCE_ID,
            acquisition_date="2026-01-13",
        ),
    )

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": RESOURCESAT_LISS3_SOURCE_ID,
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
            "preferHighRes": True,
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["resolvedSourceId"] == RESOURCESAT_LISS4_SOURCE_ID
    assert body["resolutionMeters"] == pytest.approx(5.8)
    assert body["enhanced"] is True
    assert body["basisDate"] == "2026-01-13"
    assert body.get("provenanceNote") is None


def test_statistics_response_includes_provenance_fields_when_primary(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **_kw: _fake_resolution(enhanced=False),
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: _stats_response(source_id=RESOURCESAT_LISS3_SOURCE_ID),
    )

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": RESOURCESAT_LISS3_SOURCE_ID,
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["resolvedSourceId"] == RESOURCESAT_LISS3_SOURCE_ID
    assert body["enhanced"] is False
    assert body["basisDate"] is None


def test_statistics_response_ndmi_has_provenance_note(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **_kw: ResolutionResult(
            source_id=RESOURCESAT_LISS3_SOURCE_ID,
            resolution_meters=24.0,
            enhanced=False,
            basis_date=None,
            provenance_note="Moisture served from LISS-3 (24 m) -- LISS-4 has no SWIR band.",
        ),
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: _stats_response(index_type="NDMI"),
    )

    r = client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": RESOURCESAT_LISS3_SOURCE_ID,
            "acquisitionDate": "2026-01-15",
            "indexType": "NDMI",
        },
    )

    assert r.status_code == 200
    body = r.json()
    note = body.get("provenanceNote") or ""
    assert "LISS-3" in note
    assert "SWIR" in note


def test_statistics_request_prefer_high_res_field_is_parsed(monkeypatch):
    """preferHighRes=false in request body must be forwarded to the resolver."""
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    captured: dict[str, Any] = {}

    def spy(**kw: Any) -> ResolutionResult:
        captured.update(kw)
        return _fake_resolution(enhanced=False)

    monkeypatch.setattr(field_analytics.catalog, "resolve_best_resolution_source", spy)
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **_kw: _stats_response(),
    )

    client.post(
        "/api/fields/field-1/indices/statistics",
        json={
            "sourceId": RESOURCESAT_LISS3_SOURCE_ID,
            "acquisitionDate": "2026-01-15",
            "indexType": "NDVI",
            "preferHighRes": False,
        },
    )
    assert captured.get("prefer_high_res") is False


# ---------------------------------------------------------------------------
# TEST-007 — response provenance: overlay endpoint headers
# ---------------------------------------------------------------------------


def _fake_liss4_read():
    return SimpleNamespace(
        band_arrays={
            3: np.array([[2000, 5000], [1000, 0]], dtype=np.uint16),  # NIR at pos 3
            2: np.array([[6000, 5000], [7000, 0]], dtype=np.uint16),  # RED at pos 2
        },
        mask=np.array([[1, 2], [1, 0]], dtype=np.uint8),
        geometry_mask=np.array([[True, True], [True, True]], dtype=bool),
        nodata=0,
        intersects=True,
    )


def test_overlay_headers_include_provenance_when_enhanced(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **_kw: _fake_resolution(enhanced=True, basis_date="2026-01-13"),
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "supported_indices",
        lambda *_: ["NDVI", "MSAVI", "NDWI_GREEN_NIR"],
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_assets_for_date",
        lambda *_: _liss4_assets(),
    )
    monkeypatch.setattr(field_analytics, "read_index_windows", lambda **_: _fake_liss4_read())

    r = client.get(
        "/api/fields/field-1/overlay/NDVI.png"
        f"?sourceId={RESOURCESAT_LISS3_SOURCE_ID}"
        "&acquisitionDate=2026-01-15"
        "&preferHighRes=true"
    )

    assert r.status_code == 200
    assert r.headers.get("x-akasha-resolved-source") == RESOURCESAT_LISS4_SOURCE_ID
    assert r.headers.get("x-akasha-enhanced") == "true"
    assert r.headers.get("x-akasha-basis-date") == "2026-01-13"
    # Resolution header must be present and match the LISS-4 composite grid.
    assert r.headers.get("x-akasha-resolved-resolution") == "5.8"


def test_overlay_headers_include_provenance_when_primary(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **_kw: _fake_resolution(enhanced=False),
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "supported_indices",
        lambda *_: ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_assets_for_date",
        lambda *_: [
            {
                "analyticHref": "s3://akasha-cogs/liss3/analytic.tif",
                "maskHref": "s3://akasha-cogs/liss3/mask.tif",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4", "SWIR1": "BAND5"
                },
                "scale": 0.0001,
                "offset": 0.0,
                "excludedMaskClasses": [0, 2, 3],
                "nodataPolicy": "mask_only",
                "bbox": [78.0, 12.0, 79.0, 13.0],
            }
        ],
    )
    monkeypatch.setattr(field_analytics, "read_index_windows", lambda **_: _fake_liss4_read())

    r = client.get(
        "/api/fields/field-1/overlay/NDVI.png"
        f"?sourceId={RESOURCESAT_LISS3_SOURCE_ID}"
        "&acquisitionDate=2026-01-15"
        "&preferHighRes=false"
    )

    assert r.status_code == 200
    assert r.headers.get("x-akasha-resolved-source") == RESOURCESAT_LISS3_SOURCE_ID
    assert r.headers.get("x-akasha-enhanced") == "false"
    assert "x-akasha-basis-date" not in r.headers


# ---------------------------------------------------------------------------
# TEST-007 — response provenance: point endpoint
# ---------------------------------------------------------------------------


def test_point_response_includes_provenance_fields(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_best_resolution_source",
        lambda **_kw: _fake_resolution(enhanced=True, basis_date="2026-01-13"),
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "supported_indices",
        lambda *_: ["NDVI", "MSAVI", "NDWI_GREEN_NIR"],
    )
    monkeypatch.setattr(
        field_analytics.catalog,
        "resolve_assets_for_date",
        lambda *_: _liss4_assets(),
    )
    monkeypatch.setattr(field_analytics, "read_index_windows", lambda **_: _fake_liss4_read())

    r = client.get(
        "/api/fields/field-1/indices/point"
        f"?sourceId={RESOURCESAT_LISS3_SOURCE_ID}"
        "&acquisitionDate=2026-01-15"
        "&indexType=NDVI"
        "&lng=78.202&lat=12.102"
        "&preferHighRes=true"
    )

    assert r.status_code == 200
    body = r.json()
    assert body.get("resolvedSourceId") == RESOURCESAT_LISS4_SOURCE_ID
    assert body.get("resolutionMeters") == pytest.approx(5.8)
    assert body.get("enhanced") is True
    assert body.get("basisDate") == "2026-01-13"


# ---------------------------------------------------------------------------
# TEST-007 — trend stays on primary source only
# ---------------------------------------------------------------------------


def test_trend_metadata_includes_high_res_enhancement_note(monkeypatch):
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "list_dates",
        lambda _: [{"acquisitionDate": "2026-01-15"}],
    )
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **kw: _stats_response(
            index_type=kw["index_type"], acquisition_date=kw["acquisition_date"]
        ),
    )

    r = client.get(
        "/api/fields/field-1/analytics/trend"
        "?indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
        f"&sourceId={RESOURCESAT_LISS3_SOURCE_ID}"
    )

    assert r.status_code == 200
    body = r.json()
    note = body["metadata"].get("highResEnhancementNote", "")
    assert "LISS-4" in note
    assert "single-date" in note.lower() or "single date" in note.lower()


def test_trend_uses_primary_source_not_liss4(monkeypatch):
    """Trend loop must pass prefer_high_res=False so LISS-4 is never used."""
    monkeypatch.setattr(field_analytics.fields_repo, "get_field", lambda *_: _plot())
    monkeypatch.setattr(
        field_analytics.catalog,
        "list_dates",
        lambda _: [{"acquisitionDate": "2026-01-15"}],
    )
    resolver_calls: list[bool] = []

    def spy_resolver(**kw: Any) -> ResolutionResult:
        resolver_calls.append(kw.get("prefer_high_res", True))
        return _fake_resolution(enhanced=False)

    monkeypatch.setattr(field_analytics.catalog, "resolve_best_resolution_source", spy_resolver)
    monkeypatch.setattr(
        field_analytics,
        "compute_statistics",
        lambda **kw: _stats_response(
            index_type=kw["index_type"], acquisition_date=kw["acquisition_date"]
        ),
    )

    r = client.get(
        "/api/fields/field-1/analytics/trend"
        "?indexType=NDVI&startDate=2026-01-01&endDate=2026-03-01"
    )

    assert r.status_code == 200
    # All resolver calls from the trend loop must have prefer_high_res=False.
    assert resolver_calls, "resolver should have been called"
    assert all(v is False for v in resolver_calls), (
        f"Trend resolver calls with prefer_high_res=True detected: {resolver_calls}"
    )
