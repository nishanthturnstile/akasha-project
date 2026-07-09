"""Source payload registry tests for product source availability and metadata."""

from __future__ import annotations

from app.config import settings
from app.raster import catalog_resolver as catalog
from app.raster.catalog_resolver import RESOURCESAT_AWIFS_SOURCE_ID, RESOURCESAT_LISS4_SOURCE_ID
from app.routers import product_router


def test_liss4_source_payload_is_active_after_staging_verification() -> None:
    liss4 = catalog.source_payload(RESOURCESAT_LISS4_SOURCE_ID)

    assert liss4["availabilityStatus"] == "active"
    assert liss4["gatedReason"] is None
    assert liss4["analysisLevel"] == "field"
    assert liss4["resolutionMeters"] == 5.8
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
