"""Source payload registry tests for product source availability and metadata."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from app.config import settings
from app.raster import catalog_resolver as catalog
from app.raster.catalog_resolver import (
    RESOURCESAT_AWIFS_SOURCE_ID,
    RESOURCESAT_LISS3_SOURCE_ID,
    RESOURCESAT_LISS4_SOURCE_ID,
)
from app.routers import product_router


def test_liss4_source_payload_is_active_after_staging_verification() -> None:
    liss4 = catalog.source_payload(RESOURCESAT_LISS4_SOURCE_ID)

    assert liss4["availabilityStatus"] == "active"
    assert liss4["gatedReason"] is None
    assert liss4["analysisLevel"] == "field"
    assert liss4["resolutionMeters"] == 5.8
    assert liss4["revisitDays"] == 5
    assert liss4["supportedIndices"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert "NDMI" not in liss4["supportedIndices"]
    assert "NDRE" not in liss4["supportedIndices"]
    assert "RECI" not in liss4["supportedIndices"]
    assert "NDMI" not in liss4["displayModes"]
    assert "NDRE" not in liss4["displayModes"]
    assert "RECI" not in liss4["displayModes"]
    assert "NDMI" not in liss4["mapDisplayModes"]
    assert "NDRE" not in liss4["mapDisplayModes"]
    assert "RECI" not in liss4["mapDisplayModes"]


def test_awifs_source_payload_is_active_with_regional_limitations() -> None:
    awifs = catalog.source_payload(RESOURCESAT_AWIFS_SOURCE_ID)

    assert awifs["availabilityStatus"] == "active"
    assert awifs["gatedReason"] is None
    assert awifs["analysisLevel"] == "regional"
    assert awifs["resolutionMeters"] == 56
    assert awifs["revisitDays"] == 5
    assert awifs["supportedIndices"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert awifs["displayModes"] == ["FCC", "NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert awifs["mapDisplayModes"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]
    assert awifs["defaultDisplayMode"] == "FCC"
    assert awifs["defaultMapDisplayMode"] == "NDVI"
    assert awifs["bandRoleMapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
        "SWIR1": "BAND5",
    }
    assert awifs["limitations"] == [
        "Coarse 56 m pixels; use for regional context and large-field analytics.",
        "Mask is Akasha threshold-derived and provisional until a native quality layer exists.",
        (
            "AWiFS-specific EO wavelengths are pending NRSC validation; STAC currently "
            "uses the shared ResourceSat broad-band metadata aliases."
        ),
        "Not a replacement for LISS-3/LISS-4 field-level monitoring.",
    ]


def test_resourcesat_pipeline_payload_preserves_source_specific_metadata(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ingestion_api_url", "http://ingestion.internal:18080")
    monkeypatch.setattr(settings, "ingestion_api_key", "SECRET_API_KEY")
    monkeypatch.setattr(settings, "ingestion_readiness_enabled", True)
    monkeypatch.setattr(settings, "ingestion_field_index_enabled", True)
    monkeypatch.setattr(settings, "ingestion_resourcesat_cutover_enabled", True)
    monkeypatch.setattr(
        settings,
        "ingestion_resourcesat_cutover_source_ids",
        ",".join(
            (
                RESOURCESAT_LISS3_SOURCE_ID,
                RESOURCESAT_LISS4_SOURCE_ID,
                RESOURCESAT_AWIFS_SOURCE_ID,
            )
        ),
    )

    liss4 = product_router._pipeline_source_payload(RESOURCESAT_LISS4_SOURCE_ID)
    assert liss4 is not None
    assert liss4["pipelineBacked"] is True
    assert liss4["resolutionMeters"] == 5.8
    assert liss4["displayModes"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert liss4["mapDisplayModes"] == ["NDVI", "MSAVI", "NDWI_GREEN_NIR"]
    assert "NDMI" not in liss4["supportedIndices"]
    assert "NDMI" not in liss4["displayModes"]

    awifs = product_router._pipeline_source_payload(RESOURCESAT_AWIFS_SOURCE_ID)
    assert awifs is not None
    assert awifs["pipelineBacked"] is True
    assert awifs["analysisLevel"] == "regional"
    assert awifs["resolutionMeters"] == 56
    assert awifs["displayModes"] == ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"]


@pytest.mark.parametrize(
    ("source_id", "expected_revisit_days"),
    [
        (catalog.SENTINEL_2_SOURCE_ID, 5),
        (RESOURCESAT_LISS3_SOURCE_ID, 24),
        (RESOURCESAT_LISS4_SOURCE_ID, 5),
        (RESOURCESAT_AWIFS_SOURCE_ID, 5),
        ("eos-06-ocm-lac-ndvi-8day-360m", 8),
    ],
)
def test_source_payload_exposes_validated_revisit_days(
    source_id: str,
    expected_revisit_days: int,
) -> None:
    assert catalog.source_payload(source_id)["revisitDays"] == expected_revisit_days


def test_next_expected_acquisition_advances_stale_history_until_future() -> None:
    result = product_router._next_expected_acquisition_date(
        "2026-05-19",
        5,
        today=date(2026, 7, 14),
    )

    assert result == "2026-07-18"


def test_next_expected_acquisition_advances_when_first_projection_is_today() -> None:
    result = product_router._next_expected_acquisition_date(
        "2026-07-09",
        5,
        today=date(2026, 7, 14),
    )

    assert result == "2026-07-19"


@pytest.mark.parametrize(
    ("latest", "revisit_days"),
    [(None, 5), ("not-a-date", 5), ("2026-07-14", None), ("2026-07-14", 0)],
)
def test_next_expected_acquisition_omits_invalid_or_unknown_cadence(
    latest: str | None,
    revisit_days: int | None,
) -> None:
    assert (
        product_router._next_expected_acquisition_date(
            latest,
            revisit_days,
            today=date(2026, 7, 14),
        )
        is None
    )


def test_native_default_layer_projects_from_newest_source_date_not_older_usable(
    monkeypatch,
) -> None:
    dates = [
        {
            "acquisitionDate": "2026-06-01",
            "isLatestUsable": False,
            "tileAvailable": False,
            "sceneCount": 1,
        },
        {
            "acquisitionDate": "2026-05-19",
            "isLatestUsable": True,
            "tileAvailable": True,
            "sceneCount": 1,
        },
    ]
    projection_bases: list[str | None] = []
    monkeypatch.setattr(product_router.catalog, "list_dates", lambda _source_id: dates)
    monkeypatch.setattr(product_router.catalog, "items_for_date", lambda *_args: [])
    monkeypatch.setattr(
        product_router,
        "_expected_acquisition_payload",
        lambda _source, latest: (
            projection_bases.append(latest)
            or {"revisitDays": 24, "nextExpectedAcquisitionDate": "2026-07-12"}
        ),
    )

    payload = asyncio.run(product_router.get_default_layer(RESOURCESAT_LISS3_SOURCE_ID))

    assert payload["acquisitionDate"] == "2026-05-19"
    assert projection_bases == ["2026-06-01"]


def test_native_default_layer_without_dates_keeps_projection_fields(monkeypatch) -> None:
    monkeypatch.setattr(product_router.catalog, "list_dates", lambda _source_id: [])

    payload = asyncio.run(product_router.get_default_layer(RESOURCESAT_LISS3_SOURCE_ID))

    assert payload["acquisitionDate"] is None
    assert payload["revisitDays"] == 24
    assert payload["nextExpectedAcquisitionDate"] is None


def test_hidden_unvalidated_sar_sources_are_not_bff_active() -> None:
    """BFF availability must not bypass scheduler source-state gating."""
    eos04 = catalog.source_payload("eos-04-sar-mrs-l2b")
    nisar = catalog.source_payload("nisar-ssar-beta-gcov")

    assert eos04["availabilityStatus"] == "gated"
    assert eos04["gatedReason"]
    assert nisar["availabilityStatus"] == "gated"
    assert nisar["gatedReason"]


def test_eos04_source_payload_is_display_only_sar_contract() -> None:
    eos04 = catalog.source_payload("eos-04-sar-mrs-l2b")

    assert eos04["kind"] == "sar"
    assert eos04["productRole"] == "support"
    assert eos04["availabilityStatus"] == "gated"
    assert eos04["expectedAssets"] == ["backscatter"]
    assert eos04["supportedIndices"] == []
    assert eos04["maskAsset"] is None
    assert eos04["availableMaskOptions"] == []
    assert eos04["displayModes"] == ["VV_GRAYSCALE"]
    assert eos04["defaultDisplayMode"] == "VV_GRAYSCALE"
    assert eos04["dateMetricsKind"] == "radar"
    assert eos04["defaultRescale"] == "-25,5"
    assert any("no NDVI" in limitation for limitation in eos04["limitations"])
