"""Source payload registry tests for product source availability and metadata."""

from __future__ import annotations

from app.raster import catalog_resolver as catalog
from app.raster.catalog_resolver import RESOURCESAT_AWIFS_SOURCE_ID, RESOURCESAT_LISS4_SOURCE_ID


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


def test_hidden_unvalidated_sar_sources_are_not_bff_active() -> None:
    """BFF availability must not bypass scheduler source-state gating."""
    eos04 = catalog.source_payload("eos-04-sar-mrs-l2b")
    nisar = catalog.source_payload("nisar-ssar-beta-gcov")

    assert eos04["availabilityStatus"] == "gated"
    assert eos04["gatedReason"]
    assert nisar["availabilityStatus"] == "gated"
    assert nisar["gatedReason"]
