"""Phase A: colorized index display-tile route + expression builder tests.

These exercise the new EOS-style index layers (NDVI/NDRE/MSAVI/NDMI) without
needing real COGs: the asset resolver and the TiTiler fetch are monkeypatched,
so only the BFF wiring (expression, colormap, rescale, dispatch) is under test.
"""
from __future__ import annotations

from typing import Any

from app import product
from app.main import app
from app.raster import tiles
from app.raster.indices import get_index, index_tile_expression
from fastapi.testclient import TestClient

client = TestClient(app)

# Frozen Sentinel-2 analytic band order -> positions: B04=1, B08=2, B05=3, B11=6.
_S2_BANDS = ["B04", "B08", "B05", "B06", "B07", "B11", "B12", "B03", "B02"]
_S2_ROLE_MAP = {
    "BLUE": "B02",
    "GREEN": "B03",
    "RED": "B04",
    "NIR": "B08",
    "RED_EDGE": "B05",
    "SWIR1": "B11",
    "SWIR2": "B12",
}


def _assets(**overrides: Any) -> dict[str, Any]:
    base = {
        "itemId": "item-1",
        "analyticHref": "s3://akasha-cogs/sentinel-2-l2a/x/analytic.tif",
        "bandNames": _S2_BANDS,
        "bandRoleMapping": _S2_ROLE_MAP,
        "scale": 0.0001,
        "offset": -0.1,
    }
    base.update(overrides)
    return base


def test_ndvi_expression_uses_corrected_nir_and_red_positions():
    expr = index_tile_expression(_S2_BANDS, _S2_ROLE_MAP, get_index("NDVI"))
    # NDVI = (NIR - RED)/(NIR + RED); NIR=B08=b2, RED=B04=b1, reflectance corrected.
    assert expr == "((0.0001*b2-0.1)-(0.0001*b1-0.1))/((0.0001*b2-0.1)+(0.0001*b1-0.1))"


def test_ndmi_expression_uses_swir1_position():
    expr = index_tile_expression(_S2_BANDS, _S2_ROLE_MAP, get_index("NDMI"))
    # NDMI = (NIR - SWIR1)/(NIR + SWIR1); NIR=b2, SWIR1=B11=b6.
    assert "b6" in expr and "b2" in expr


def test_msavi_expression_is_msavi_shape():
    expr = index_tile_expression(_S2_BANDS, _S2_ROLE_MAP, get_index("MSAVI"))
    assert expr.startswith("(2*") and "sqrt(" in expr


def test_source_payload_exposes_layer_groups_for_sentinel2():
    s2 = product.catalog.source_payload("sentinel-2-l2a")
    assert "NDVI" in s2["displayModes"]
    assert "NDMI" in s2["displayModes"]
    assert s2["defaultDisplayMode"] == "RGB"  # never default to an index layer
    labels = [g["label"] for g in s2["layerGroups"]]
    assert labels == ["Natural Color", "Vegetation Indices", "Moisture Indices"]


def test_index_tile_route_renders_colorized_ndvi(monkeypatch):
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        product.catalog, "resolve_assets_for_date", lambda *_: [_assets()]
    )

    def fake_fetch(url: str, *_a, **_k):
        captured["url"] = url
        return b"PNGDATA", "image/png"

    monkeypatch.setattr(tiles, "fetch_tile", fake_fetch)

    r = client.get("/api/tiles/sentinel-2-l2a/2025-09-14/ndvi/12/2059/1907.png")

    assert r.status_code == 200
    assert r.content == b"PNGDATA"
    # TiTiler request carries the NDVI expression + colormap + rescale.
    assert "expression=" in captured["url"]
    assert "colormap_name=rdylgn" in captured["url"]
    assert "rescale=-0.2%2C0.9" in captured["url"]  # urlencoded "-0.2,0.9"


def test_unsupported_index_display_mode_is_rejected():
    # NDWI_GREEN_NIR is a supported index but NOT in Sentinel-2 displayModes.
    r = client.get("/api/tiles/sentinel-2-l2a/2025-09-14/ndwi_green_nir/12/2059/1907.png")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_DISPLAY_MODE"
