from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import eos04_pipeline  # noqa: E402


def test_eos04_validation_loads_collection_before_items(monkeypatch, tmp_path):
    raster_root = tmp_path / "rasters"
    temp_root = tmp_path / "work"
    raw_root = tmp_path / "raw"
    ledger_path = tmp_path / "ledger.sqlite"
    product_id = "EOS04_TEST_20260622T053000"
    order: list[str] = []

    monkeypatch.setenv("RASTER_SOURCE_DIR", str(raster_root))
    monkeypatch.setattr("akasha_ingest.config.BHOONIDHI_TEMP_ROOT", str(temp_root))
    monkeypatch.setattr("akasha_ingest.config.BHOONIDHI_RAW_ROOT", str(raw_root))
    monkeypatch.setattr("akasha_ingest.config.BHOONIDHI_LEDGER_PATH", str(ledger_path))

    class FakeClient:
        def search(self, **_kwargs):
            return [
                {
                    "id": product_id,
                    "bbox": [77.2, 12.2, 77.8, 12.8],
                    "properties": {"Online": "Y", "datetime": "2026-06-22T05:30:00Z"},
                }
            ]

        def download_product(self, *, product_id: str, collection: str, destination: Path):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"zip")
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 3}

        def logout(self, **_kwargs):
            return None

    monkeypatch.setattr("akasha_ingest.bhoonidhi.BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr("akasha_ingest.storage.ensure_bucket", lambda: "bucket exists")
    monkeypatch.setattr(
        "akasha_ingest.storage.seed_manifest_cogs",
        lambda *_args, **_kwargs: ["uploaded"],
    )
    monkeypatch.setattr(
        "akasha_ingest.storage.verify_manifest_cogs", lambda *_args: (True, "verified")
    )
    monkeypatch.setattr(
        "akasha_ingest.catalog.load_collection",
        lambda **_kwargs: order.append("load_collection") or "collection loaded",
    )
    monkeypatch.setattr(
        "akasha_ingest.catalog.load_manifest_items",
        lambda *_args, **_kwargs: order.append("load_manifest_items") or "items loaded",
    )

    def prepare_fn(_download_manifest_path: Path) -> None:
        out_dir = (
            raster_root
            / eos04_pipeline.EOS04_SAR_SOURCE_ID
            / "2026-06-22"
            / "unknown"
            / product_id
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "prepare_manifest.json").write_text(
            json.dumps(
                {
                    "source_id": eos04_pipeline.EOS04_SAR_SOURCE_ID,
                    "product_id": product_id,
                    "acquisition_datetime": "2026-06-22T05:30:00Z",
                    "acquisition_date": "2026-06-22",
                    "sar:polarizations": ["HH", "HV"],
                    "outputs": {
                        "backscatter": {
                            "path": "backscatter.tif",
                            "dtype": "float32",
                            "band_count": 2,
                            "nodata": -9999.0,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    result = eos04_pipeline.run_eos04_validation(
        eos04_pipeline.Eos04ValidationParams(
            source_id=eos04_pipeline.EOS04_SAR_SOURCE_ID,
                aoi={
                    "bbox": [77.0, 12.0, 78.0, 13.0],
                    "geometry": {"type": "Polygon"},
                },
            aoi_id="bangalore-60km",
            window_start="2026-05-17",
            window_end="2026-06-30",
            datetime_range="2026-05-17T00:00:00Z/2026-06-30T23:59:59Z",
            max_downloads=1,
        ),
        prepare_fn=prepare_fn,
    )

    assert result.verdict == "succeeded"
    assert result.ingested is True
    assert order == ["load_collection", "load_manifest_items"]
