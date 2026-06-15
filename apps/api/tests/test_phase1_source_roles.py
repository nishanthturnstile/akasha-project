"""Phase 1 source-aware index role tests."""

from __future__ import annotations

import numpy as np
import pytest
from app.raster import catalog_resolver as catalog
from app.raster import service
from app.raster.raster_reader import WindowRead

IN_FOOTPRINT_POLY = {
    "type": "Polygon",
    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]],
}


def test_resourcesat_msavi_resolves_roles_to_liss3_band_positions(monkeypatch):
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    captured_positions: list[int] = []

    monkeypatch.setattr(
        catalog,
        "supported_indices",
        lambda source_id="resourcesat-2a-liss3-boa": ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
    )
    monkeypatch.setattr(
        catalog,
        "resolve_assets_for_date",
        lambda source_id, acquisition_date: [
            {
                "itemId": "resourcesat-test",
                "analyticHref": "s3://akasha-cogs/resourcesat/analytic.tif",
                "sclHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "maskHref": "s3://akasha-cogs/resourcesat/mask.tif",
                "maskAsset": "mask",
                "bandNames": ["BAND2", "BAND3", "BAND4", "BAND5"],
                "bandRoleMapping": {
                    "GREEN": "BAND2",
                    "RED": "BAND3",
                    "NIR": "BAND4",
                    "SWIR1": "BAND5",
                },
                "scale": 0.0001,
                "offset": 0.0,
                "nodata": 0,
                "bbox": None,
            }
        ],
    )

    def fake_read_index_windows(*, analytic_href, mask_href, geometry, positions):
        captured_positions.extend(positions)
        return WindowRead(
            band_arrays={
                2: np.full((2, 2), 2000, dtype="uint16"),
                3: np.full((2, 2), 6000, dtype="uint16"),
            },
            mask=np.full((2, 2), 4, dtype="uint8"),
            geometry_mask=np.ones((2, 2), dtype=bool),
            nodata=0,
            height=2,
            width=2,
            intersects=True,
        )

    monkeypatch.setattr(service, "read_index_windows", fake_read_index_windows)

    resp = service.compute_statistics(
        geometry=IN_FOOTPRINT_POLY,
        source_id="resourcesat-2a-liss3-boa",
        acquisition_date="2026-01-15",
        index_type="MSAVI",
        max_area_ha=50,
        max_vertices=5000,
    )

    nir = 0.6
    red = 0.2
    expected = (2 * nir + 1 - np.sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))) / 2
    assert captured_positions == [3, 2]
    assert resp["statistics"]["mean"] == pytest.approx(expected)
    assert resp["metadata"]["bands"] == ["BAND4", "BAND3"]
    assert resp["metadata"]["spectralRoles"] == ["NIR", "RED"]
