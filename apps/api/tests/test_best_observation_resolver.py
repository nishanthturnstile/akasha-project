"""Tests for the generalized best-observation resolver (Phase 11 / TASK-066–069).

Covers:
- Pure _observation_score unit tests (no catalog I/O).
- resolve_best_observation unit tests with mocked catalog (no raster reads).
- AWiFS exclusion / allow_coarse logic.
- Index-filter exclusion.
- Date-window filtering.
- Field-geometry bbox intersection filtering.
- Gated source exclusion.
- API endpoint smoke tests via TestClient (import/routing verification).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from app.main import app
from app.raster.catalog_resolver import (
    RESOURCESAT_AWIFS_SOURCE_ID,
    RESOURCESAT_LISS3_SOURCE_ID,
    RESOURCESAT_LISS4_SOURCE_ID,
    ObservationCandidate,
    _observation_score,
    resolve_best_observation,
)
from fastapi.testclient import TestClient

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_FIELD_POLY = {
    "type": "Polygon",
    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]],
}

_LISS3_DATE: dict[str, Any] = {
    "acquisitionDate": "2026-01-15",
    "bounds": [78.0, 12.0, 79.0, 13.0],
    "tileAvailable": True,
    "isLatestUsable": True,
    "usablePixelPercent": 85.0,
    "coveragePercent": 92.0,
    "cloudMaskedPercent": 8.0,
}

_LISS4_DATE: dict[str, Any] = {
    "acquisitionDate": "2026-01-14",
    "bounds": [78.0, 12.0, 79.0, 13.0],
    "tileAvailable": True,
    "isLatestUsable": True,
    "usablePixelPercent": 88.0,
    "coveragePercent": 95.0,
    "cloudMaskedPercent": 5.0,
}

_AWIFS_DATE: dict[str, Any] = {
    "acquisitionDate": "2026-01-15",
    "bounds": [77.0, 11.0, 80.0, 14.0],
    "tileAvailable": True,
    "isLatestUsable": True,
    "usablePixelPercent": 70.0,
    "coveragePercent": 80.0,
    "cloudMaskedPercent": 12.0,
}


def _make_source(source_id: str, **overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "id": source_id,
        "label": source_id,
        "kind": "optical",
        "supportedIndices": ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
        "availabilityStatus": "active",
        "analysisLevel": "field",
        "resolutionMeters": 24.0,
        "bandRoleMapping": {},
        "displayModes": ["FCC"],
        "defaultDisplayMode": "FCC",
        "description": "test",
        "attribution": "test",
        "dateMetricsKind": "optical",
        "defaultRescale": "0,3000",
        "tileRouteMode": "fcc",
        "collectionId": source_id,
        "expectedAssets": ["analytic", "mask"],
        "maskAsset": "mask",
    }
    defaults.update(overrides)
    return defaults


def _mock_list_dates(source_id: str) -> list[dict[str, Any]]:
    return {
        RESOURCESAT_LISS3_SOURCE_ID: [_LISS3_DATE],
        RESOURCESAT_LISS4_SOURCE_ID: [_LISS4_DATE],
        RESOURCESAT_AWIFS_SOURCE_ID: [_AWIFS_DATE],
    }.get(source_id, [])


def _mock_get_source(source_id: str) -> dict[str, Any]:
    if source_id == RESOURCESAT_LISS3_SOURCE_ID:
        return _make_source(RESOURCESAT_LISS3_SOURCE_ID, resolutionMeters=24.0)
    if source_id == RESOURCESAT_LISS4_SOURCE_ID:
        return _make_source(
            RESOURCESAT_LISS4_SOURCE_ID,
            resolutionMeters=5.8,
            supportedIndices=["NDVI", "MSAVI", "NDWI_GREEN_NIR"],
        )
    if source_id == RESOURCESAT_AWIFS_SOURCE_ID:
        return _make_source(
            RESOURCESAT_AWIFS_SOURCE_ID,
            resolutionMeters=56.0,
            analysisLevel="regional",
            availabilityStatus="active",
        )
    raise KeyError(f"Unknown source: {source_id}")


def _mock_selectable_ids() -> list[str]:
    return [
        RESOURCESAT_LISS4_SOURCE_ID,
        RESOURCESAT_LISS3_SOURCE_ID,
        RESOURCESAT_AWIFS_SOURCE_ID,
    ]


@pytest.fixture()
def _mock_catalog():
    with (
        patch(
            "app.raster.catalog_resolver.selectable_source_ids",
            side_effect=_mock_selectable_ids,
        ),
        patch(
            "app.raster.catalog_resolver.get_source",
            side_effect=_mock_get_source,
        ),
        patch(
            "app.raster.catalog_resolver.list_dates",
            side_effect=_mock_list_dates,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# _observation_score unit tests
# ---------------------------------------------------------------------------


def test_score_exact_date_high_priority() -> None:
    score = _observation_score(
        source_priority=80,
        days_diff=0,
        usable_pixel_percent=90.0,
        coverage_percent=95.0,
        window_days=30,
    )
    # 0.4*80 + 0.35*100 + 0.15*90 + 0.10*95 = 32 + 35 + 13.5 + 9.5 = 90
    assert abs(score - 90.0) < 0.01


def test_score_low_priority_exact_date() -> None:
    score = _observation_score(
        source_priority=20,
        days_diff=0,
        usable_pixel_percent=50.0,
        coverage_percent=50.0,
        window_days=30,
    )
    # 0.4*20 + 0.35*100 + 0.15*50 + 0.10*50 = 8 + 35 + 7.5 + 5 = 55.5
    assert abs(score - 55.5) < 0.01


def test_score_at_window_boundary() -> None:
    score = _observation_score(
        source_priority=80,
        days_diff=30,
        usable_pixel_percent=80.0,
        coverage_percent=80.0,
        window_days=30,
    )
    # proximity = 100 - 30*(100/30) = 0
    # 0.4*80 + 0.35*0 + 0.15*80 + 0.10*80 = 32 + 0 + 12 + 8 = 52
    assert abs(score - 52.0) < 0.01


def test_score_unknown_quality_defaults_neutral() -> None:
    score_known = _observation_score(
        source_priority=80,
        days_diff=0,
        usable_pixel_percent=50.0,
        coverage_percent=50.0,
        window_days=30,
    )
    score_unknown = _observation_score(
        source_priority=80,
        days_diff=0,
        usable_pixel_percent=None,
        coverage_percent=None,
        window_days=30,
    )
    assert abs(score_known - score_unknown) < 0.01, "None quality should default to 50 neutral"


def test_liss4_scores_higher_than_liss3_same_date() -> None:
    score_liss4 = _observation_score(
        source_priority=100,
        days_diff=0,
        usable_pixel_percent=80.0,
        coverage_percent=80.0,
        window_days=30,
    )
    score_liss3 = _observation_score(
        source_priority=80,
        days_diff=0,
        usable_pixel_percent=80.0,
        coverage_percent=80.0,
        window_days=30,
    )
    assert score_liss4 > score_liss3, "LISS-4 (priority=100) must outscore LISS-3 (priority=80)"


def test_score_beyond_window_clamps_proximity_to_zero() -> None:
    score_inside = _observation_score(
        source_priority=50,
        days_diff=0,
        usable_pixel_percent=50.0,
        coverage_percent=50.0,
        window_days=30,
    )
    score_outside = _observation_score(
        source_priority=50,
        days_diff=60,  # well beyond window_days=30
        usable_pixel_percent=50.0,
        coverage_percent=50.0,
        window_days=30,
    )
    assert score_inside > score_outside, "Older dates must score lower due to proximity penalty"


# ---------------------------------------------------------------------------
# resolve_best_observation unit tests with mocked catalog
# ---------------------------------------------------------------------------


def test_liss4_preferred_over_liss3(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(target_date="2026-01-15", index_type="NDVI")
    assert candidates, "Expected at least one candidate"
    assert (
        candidates[0].source_id == RESOURCESAT_LISS4_SOURCE_ID
    ), f"Expected LISS-4 first (highest priority+usable), got {candidates[0].source_id}"


def test_awifs_excluded_field_use_case(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(target_date="2026-01-15", use_case="field")
    ids = {c.source_id for c in candidates}
    assert RESOURCESAT_AWIFS_SOURCE_ID not in ids, "AWiFS must be excluded for field use case"


def test_awifs_included_when_allow_coarse(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(
        target_date="2026-01-15",
        use_case="field",
        allow_coarse=True,
    )
    ids = {c.source_id for c in candidates}
    assert RESOURCESAT_AWIFS_SOURCE_ID in ids, "AWiFS must be included when allow_coarse=True"


def test_awifs_included_for_regional_use_case(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(target_date="2026-01-15", use_case="regional")
    ids = {c.source_id for c in candidates}
    assert RESOURCESAT_AWIFS_SOURCE_ID in ids, "AWiFS must appear in regional use case"


def test_index_filter_excludes_liss4_for_ndmi(_mock_catalog: None) -> None:
    # LISS-4 does not support NDMI (no SWIR band).
    candidates = resolve_best_observation(target_date="2026-01-15", index_type="NDMI")
    ids = {c.source_id for c in candidates}
    assert RESOURCESAT_LISS4_SOURCE_ID not in ids, "LISS-4 must not appear for NDMI"
    assert RESOURCESAT_LISS3_SOURCE_ID in ids, "LISS-3 supports NDMI and must appear"


def test_date_window_excludes_out_of_range(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(
        start_date="2025-01-01",
        end_date="2025-12-31",
    )
    assert candidates == [], "No candidates should match a window entirely before mock dates"


def test_gated_source_excluded(_mock_catalog: None) -> None:
    """Sources with availabilityStatus != 'active' must not appear."""
    with patch(
        "app.raster.catalog_resolver.get_source",
        side_effect=lambda sid: _make_source(
            sid,
            availabilityStatus="gated" if sid == RESOURCESAT_LISS4_SOURCE_ID else "active",
            analysisLevel="field",
            resolutionMeters=5.8 if sid == RESOURCESAT_LISS4_SOURCE_ID else 24.0,
            supportedIndices=(
                ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
                if sid == RESOURCESAT_LISS4_SOURCE_ID
                else ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
            ),
        ),
    ):
        candidates = resolve_best_observation(target_date="2026-01-15")
        ids = {c.source_id for c in candidates}
        assert RESOURCESAT_LISS4_SOURCE_ID not in ids, "Gated LISS-4 must not appear"


def test_sar_source_excluded_even_if_product_active(_mock_catalog: None) -> None:
    """Best-observation remains an optical analytics resolver, not SAR display selection."""
    sar_id = "eos-04-sar-mrs-l2b"

    def selectable_with_sar() -> list[str]:
        return [sar_id, *_mock_selectable_ids()]

    def source_with_sar(source_id: str) -> dict[str, Any]:
        if source_id == sar_id:
            return _make_source(
                sar_id,
                kind="sar",
                supportedIndices=[],
                availabilityStatus="active",
                analysisLevel="context",
                resolutionMeters=None,
                displayModes=["VV_GRAYSCALE"],
                defaultDisplayMode="VV_GRAYSCALE",
                expectedAssets=["backscatter"],
                maskAsset=None,
            )
        return _mock_get_source(source_id)

    def dates_with_sar(source_id: str) -> list[dict[str, Any]]:
        if source_id == sar_id:
            return [{**_LISS3_DATE, "usablePixelPercent": None, "cloudMaskedPercent": None}]
        return _mock_list_dates(source_id)

    with (
        patch("app.raster.catalog_resolver.selectable_source_ids", side_effect=selectable_with_sar),
        patch("app.raster.catalog_resolver.get_source", side_effect=source_with_sar),
        patch("app.raster.catalog_resolver.list_dates", side_effect=dates_with_sar),
    ):
        candidates = resolve_best_observation(target_date="2026-01-15")

    assert sar_id not in {c.source_id for c in candidates}


def test_field_geometry_far_away_excluded(_mock_catalog: None) -> None:
    """Dates whose bounds bbox does not intersect the field are excluded."""
    far_field = {
        "type": "Polygon",
        "coordinates": [[[88.0, 22.0], [88.1, 22.0], [88.1, 22.1], [88.0, 22.0]]],
    }
    candidates = resolve_best_observation(
        target_date="2026-01-15",
        field_geometry=far_field,
    )
    assert candidates == [], "No candidates should match a field outside all mock bboxes"


def test_field_geometry_nearby_included(_mock_catalog: None) -> None:
    """A field inside the mock bounds should find candidates."""
    candidates = resolve_best_observation(
        target_date="2026-01-15",
        field_geometry=_FIELD_POLY,
    )
    assert candidates, "Field inside bounds should yield candidates"


def test_max_candidates_respected(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(
        target_date="2026-01-15",
        allow_coarse=True,
        max_candidates=2,
    )
    assert len(candidates) <= 2, "max_candidates must be respected"


def test_candidates_ordered_by_score_descending(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(
        target_date="2026-01-15",
        allow_coarse=True,
    )
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True), "Candidates must be ordered best-first"


def test_no_target_date_does_not_crash(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(index_type="NDVI")
    assert isinstance(candidates, list), "No-target-date call must return a list"


def test_lookback_without_target_is_anchored_to_today(_mock_catalog: None) -> None:
    with patch("app.raster.catalog_resolver._date") as mock_date:
        from datetime import date as real_date

        mock_date.today.return_value = real_date(2026, 1, 20)
        mock_date.fromisoformat.side_effect = real_date.fromisoformat
        candidates = resolve_best_observation(lookback_days=10, index_type="NDVI")

    assert candidates, "Mock dates inside the last 10 days should be included"


def test_lookback_without_target_excludes_old_history(_mock_catalog: None) -> None:
    with patch("app.raster.catalog_resolver._date") as mock_date:
        from datetime import date as real_date

        mock_date.today.return_value = real_date(2026, 3, 1)
        mock_date.fromisoformat.side_effect = real_date.fromisoformat
        candidates = resolve_best_observation(lookback_days=10, index_type="NDVI")

    assert candidates == [], "Lookback-only queries must not scan the full catalog history"


def test_lookback_with_target_does_not_include_future_observations(_mock_catalog: None) -> None:
    future_date = {**_LISS3_DATE, "acquisitionDate": "2026-01-20"}

    def list_dates_with_future(source_id: str) -> list[dict[str, Any]]:
        if source_id == RESOURCESAT_LISS3_SOURCE_ID:
            return [_LISS3_DATE, future_date]
        return _mock_list_dates(source_id)

    with patch("app.raster.catalog_resolver.list_dates", side_effect=list_dates_with_future):
        candidates = resolve_best_observation(
            target_date="2026-01-15",
            lookback_days=10,
            index_type="NDVI",
            allow_coarse=True,
        )

    assert all(c.acquisition_date <= "2026-01-15" for c in candidates)


def test_start_only_window_is_capped_at_today(_mock_catalog: None) -> None:
    future_date = {**_LISS3_DATE, "acquisitionDate": "2026-01-20"}

    def list_dates_with_future(source_id: str) -> list[dict[str, Any]]:
        if source_id == RESOURCESAT_LISS3_SOURCE_ID:
            return [_LISS3_DATE, future_date]
        return _mock_list_dates(source_id)

    with (
        patch("app.raster.catalog_resolver._date") as mock_date,
        patch("app.raster.catalog_resolver.list_dates", side_effect=list_dates_with_future),
    ):
        from datetime import date as real_date

        mock_date.today.return_value = real_date(2026, 1, 16)
        mock_date.fromisoformat.side_effect = real_date.fromisoformat
        candidates = resolve_best_observation(start_date="2026-01-01", index_type="NDVI")

    assert all(c.acquisition_date <= "2026-01-16" for c in candidates)


def test_tile_unavailable_candidates_are_excluded(_mock_catalog: None) -> None:
    unavailable = {**_LISS4_DATE, "tileAvailable": False}

    def list_dates_with_unavailable_liss4(source_id: str) -> list[dict[str, Any]]:
        if source_id == RESOURCESAT_LISS4_SOURCE_ID:
            return [unavailable]
        return _mock_list_dates(source_id)

    with patch(
        "app.raster.catalog_resolver.list_dates",
        side_effect=list_dates_with_unavailable_liss4,
    ):
        candidates = resolve_best_observation(target_date="2026-01-15", index_type="NDVI")

    assert candidates
    assert RESOURCESAT_LISS4_SOURCE_ID not in {c.source_id for c in candidates}


def test_field_geometry_requires_candidate_bounds(_mock_catalog: None) -> None:
    no_bounds_date = {key: value for key, value in _LISS3_DATE.items() if key != "bounds"}

    def list_dates_without_bounds(source_id: str) -> list[dict[str, Any]]:
        if source_id == RESOURCESAT_LISS3_SOURCE_ID:
            return [no_bounds_date]
        return []

    with patch("app.raster.catalog_resolver.list_dates", side_effect=list_dates_without_bounds):
        candidates = resolve_best_observation(
            target_date="2026-01-15",
            field_geometry=_FIELD_POLY,
            index_type="NDVI",
        )

    assert candidates == []


def test_field_geometry_rejects_invalid_candidate_bounds(_mock_catalog: None) -> None:
    invalid_bounds_date = {**_LISS3_DATE, "bounds": ["bad", 12.0, 79.0, 13.0]}

    def list_dates_with_invalid_bounds(source_id: str) -> list[dict[str, Any]]:
        if source_id == RESOURCESAT_LISS3_SOURCE_ID:
            return [invalid_bounds_date]
        return []

    with patch(
        "app.raster.catalog_resolver.list_dates",
        side_effect=list_dates_with_invalid_bounds,
    ):
        candidates = resolve_best_observation(
            target_date="2026-01-15",
            field_geometry=_FIELD_POLY,
            index_type="NDVI",
        )

    assert candidates == []


def test_is_coarse_flag_set_for_awifs(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(
        target_date="2026-01-15",
        allow_coarse=True,
    )
    awifs = [c for c in candidates if c.source_id == RESOURCESAT_AWIFS_SOURCE_ID]
    assert awifs, "AWiFS must be present with allow_coarse=True"
    assert awifs[0].is_coarse, "AWiFS candidate must have is_coarse=True"


def test_liss3_liss4_not_coarse(_mock_catalog: None) -> None:
    candidates = resolve_best_observation(target_date="2026-01-15")
    for c in candidates:
        if c.source_id in (RESOURCESAT_LISS3_SOURCE_ID, RESOURCESAT_LISS4_SOURCE_ID):
            assert not c.is_coarse, f"{c.source_id} must not be flagged as coarse"


def test_candidate_dataclass_fields(_mock_catalog: None) -> None:
    """Verify ObservationCandidate has the expected fields."""
    candidates = resolve_best_observation(target_date="2026-01-15")
    c = candidates[0]
    assert isinstance(c, ObservationCandidate)
    assert isinstance(c.source_id, str)
    assert isinstance(c.acquisition_date, str)
    assert isinstance(c.score, float)
    assert isinstance(c.supported_indices, list)
    assert isinstance(c.label, str)
    assert 0.0 <= c.score <= 100.0, "Score must be in [0, 100]"


# ---------------------------------------------------------------------------
# API endpoint smoke tests
# ---------------------------------------------------------------------------


def test_observations_router_importable() -> None:
    from app.routers.observations_router import router  # noqa: F401

    assert router is not None


def test_get_best_observations_route_exists() -> None:
    """GET /api/observations/best must be reachable (may return empty candidates)."""
    resp = client.get("/api/observations/best")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "candidates" in data
    assert "query" in data
    assert isinstance(data["candidates"], list)


def test_get_best_observations_with_target_date() -> None:
    resp = client.get("/api/observations/best?targetDate=2026-01-15&indexType=NDVI")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "candidates" in data
    assert data["query"]["indexType"] == "NDVI"
    assert data["query"]["targetDate"] == "2026-01-15"


def test_get_best_observations_invalid_date() -> None:
    resp = client.get("/api/observations/best?targetDate=not-a-date")
    assert resp.status_code == 400, f"Expected 400 for bad date, got {resp.status_code}"
    body = resp.json()
    assert body["error"]["code"] == "INVALID_DATE_PARAM"


def test_post_resolve_observation_smoke() -> None:
    """POST /api/observations/resolve must accept a geometry body."""
    payload = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]],
        },
        "targetDate": "2026-01-15",
        "indexType": "NDVI",
    }
    resp = client.post("/api/observations/resolve", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "best" in data
    assert "candidates" in data
    assert "query" in data


def test_post_resolve_invalid_target_date() -> None:
    payload = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.1]]],
        },
        "targetDate": "bad-date",
    }
    resp = client.post("/api/observations/resolve", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_DATE_PARAM"


def test_app_routes_include_observations() -> None:
    """Verify observations routes are wired into the FastAPI app."""
    paths = [r.path for r in app.routes]  # type: ignore[attr-defined]
    obs_paths = [p for p in paths if "observations" in p]
    assert obs_paths, f"Expected /api/observations/* routes, found none in: {paths}"


# ---------------------------------------------------------------------------
# TASK-072: Additional tests proving ranking factors and GET/POST consistency
# ---------------------------------------------------------------------------


def test_analysis_level_coarse_excluded_from_field_queries(_mock_catalog: None) -> None:
    """A source with analysisLevel='context' is treated as coarse and excluded from field queries.

    This proves that ranking respects analysis_level as a coarse-exclusion signal
    (not just membership in _COARSE_SOURCES).
    """

    def _patched_get_source(sid: str) -> dict[str, Any]:
        src = _mock_get_source(sid)
        if sid == RESOURCESAT_LISS3_SOURCE_ID:
            return dict(src, analysisLevel="context")
        return src

    with patch("app.raster.catalog_resolver.get_source", side_effect=_patched_get_source):
        candidates = resolve_best_observation(target_date="2026-01-15", use_case="field")
        ids = {c.source_id for c in candidates}
        assert (
            RESOURCESAT_LISS3_SOURCE_ID not in ids
        ), "LISS-3 with analysisLevel=context must be excluded for field use case"
        # LISS-4 (analysisLevel=field by default) should still appear.
        assert (
            RESOURCESAT_LISS4_SOURCE_ID in ids
        ), "LISS-4 must still appear when only LISS-3 is demoted to context"


def test_resolution_meters_present_in_candidates(_mock_catalog: None) -> None:
    """resolution_meters is correctly populated from the source registry on every candidate.

    This proves the ranking pipeline carries resolution through to ObservationCandidate,
    which the frontend uses to build provenance labels (e.g. 'LISS-4 · 5.8 m').
    """
    candidates = resolve_best_observation(target_date="2026-01-15", allow_coarse=True)
    by_source = {c.source_id: c for c in candidates}
    liss4 = by_source.get(RESOURCESAT_LISS4_SOURCE_ID)
    liss3 = by_source.get(RESOURCESAT_LISS3_SOURCE_ID)
    awifs = by_source.get(RESOURCESAT_AWIFS_SOURCE_ID)
    assert liss4 is not None, "LISS-4 must appear with allow_coarse=True"
    assert liss3 is not None, "LISS-3 must appear"
    assert awifs is not None, "AWiFS must appear with allow_coarse=True"
    assert abs((liss4.resolution_meters or 0) - 5.8) < 0.01, "LISS-4 resolution must be 5.8 m"
    assert abs((liss3.resolution_meters or 0) - 24.0) < 0.01, "LISS-3 resolution must be 24.0 m"
    assert abs((awifs.resolution_meters or 0) - 56.0) < 0.01, "AWiFS resolution must be 56.0 m"


def test_get_and_post_consistent_top_candidate(_mock_catalog: None) -> None:
    """GET /api/observations/best and POST /api/observations/resolve agree on the top source.

    Outcome 3: both endpoints must surface consistent source/date candidates because they
    share the same resolve_best_observation() backend.  The top candidate source must match.
    The POST /resolve 'best' field must equal the top GET candidate.
    """
    get_resp = client.get("/api/observations/best?targetDate=2026-01-15&maxCandidates=3")
    post_resp = client.post(
        "/api/observations/resolve",
        json={
            "geometry": _FIELD_POLY,
            "targetDate": "2026-01-15",
            "maxCandidates": 3,
        },
    )
    assert get_resp.status_code == 200, get_resp.text
    assert post_resp.status_code == 200, post_resp.text
    get_data = get_resp.json()
    post_data = post_resp.json()
    assert get_data["candidates"], "GET /best must return at least one candidate"
    assert post_data["candidates"], "POST /resolve must return at least one candidate"
    assert (
        get_data["candidates"][0]["sourceId"] == post_data["candidates"][0]["sourceId"]
    ), "GET /best and POST /resolve must agree on the top candidate source"
    assert post_data["best"] is not None, "POST /resolve must expose a 'best' field"
    assert (
        post_data["best"]["sourceId"] == get_data["candidates"][0]["sourceId"]
    ), "POST /resolve 'best' must match the top GET /best candidate"
