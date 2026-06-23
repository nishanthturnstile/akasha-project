"""Source payload registry tests for product source availability and metadata."""

from __future__ import annotations

from app.raster import catalog_resolver as catalog
from app.raster.catalog_resolver import RESOURCESAT_LISS4_SOURCE_ID


def test_liss4_source_payload_is_gated_until_staging_verification() -> None:
    liss4 = catalog.source_payload(RESOURCESAT_LISS4_SOURCE_ID)

    assert liss4["availabilityStatus"] == "gated"
    assert liss4["gatedReason"] == "LISS-4 awaits staging composite verification."
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
