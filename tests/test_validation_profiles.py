"""Phase 6 validation-profile tests.

Implements TASK-039, TASK-040, and TASK-040A from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

TASK-039 — verify-composite rejects SAR/context/archive sources with an
    actionable error pointing to verify-raster-product.

TASK-040 — verify-raster-product accepts valid SAR/context manifest fixtures
    and rejects wrong band counts or optical-index metadata on SAR sources.

TASK-040A — ResourceSat LISS-3 invariant tests proving the scheduler/
    validation refactor preserves:
    - 4-band order [BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1] / roles
    - FCC display metadata NIR/RED/GREEN
    - Akasha threshold mask v1 / no-SCL mask semantics
    - {1,4} valid mask policy / excluded {0,2,3}
    - scale 0.0001, offset 0.0
    - separate analytic/mask COG assets
    - deterministic STAC item keys
    - STAC upsert semantics (required fields present)

No rasterio/GDAL required: all core tests use manifest-metadata fixtures only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import catalog  # noqa: E402
from akasha_ingest.validation_profiles import (  # noqa: E402
    LISS3_BAND_COUNT,
    LISS3_BAND_ROLES,
    LISS3_EXPECTED_ASSETS,
    LISS3_FCC_DISPLAY_ROLES,
    LISS3_MASK_EXCLUDED_CLASSES,
    LISS3_MASK_VALID_CLASSES,
    LISS3_NODATA,
    LISS3_OFFSET,
    LISS3_SCALE,
    LISS3_SUPPORTED_STATS,
    ManifestValidationResult,
    ValidationProfileSpec,
    check_source_statistics_role,
    get_validation_profile,
    profile_for_source,
    validate_manifest_metadata,
)

WORKER_PATH = INGESTION_ROOT / "worker.py"
_worker_spec = importlib.util.spec_from_file_location(
    "akasha_worker_for_validation_tests", WORKER_PATH
)
assert _worker_spec and _worker_spec.loader
worker = importlib.util.module_from_spec(_worker_spec)
_worker_spec.loader.exec_module(worker)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Shared manifest fixtures
# ---------------------------------------------------------------------------


def _sar_manifest(source_id: str = "eos-04-sar-mrs-l2b", **extra) -> dict:
    """Minimal valid SAR prepare-manifest for eos-04 or similar sources."""
    m = {
        "source_id": source_id,
        "sar:polarizations": ["HH"],
        "outputs": {
            "backscatter": {
                "path": "backscatter.tif",
                "band_count": 1,
                "dtype": "float32",
            }
        },
    }
    m.update(extra)
    return m


def _context_manifest(source_id: str = "eos-06-ocm-lac-ndvi-8day-360m", **extra) -> dict:
    """Minimal valid context prepare-manifest."""
    m = {
        "source_id": source_id,
        "outputs": {
            "context": {
                "path": "context.tif",
                "band_count": 1,
                "dtype": "float32",
            }
        },
    }
    m.update(extra)
    return m


def _liss3_manifest(band_count: int = 4, **extra) -> dict:
    """LISS-3 BOA composite prepare-manifest fixture."""
    m = {
        "source_id": "resourcesat-2a-liss3-boa",
        "composite": True,
        "aoi_id": "bangalore-60km",
        "composite_date": "2026-03-31",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "composite_resolution_meters": 23.5,
        "composite_grid_crs": "EPSG:32643",
        "composite_grid_bounds": [716000.0, 1385000.0, 721800.0, 1390800.0],
        "composite_grid_dimensions": [246, 246],
        "analytic_band_order": ["BAND2", "BAND3", "BAND4", "BAND5"],
        "band_role_mapping": {
            "GREEN": "BAND2",
            "RED": "BAND3",
            "NIR": "BAND4",
            "SWIR1": "BAND5",
        },
        "contributing_scenes": ["scene-a"],
        "bbox": [77.0, 12.0, 78.0, 13.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 12.0], [78.0, 12.0], [78.0, 13.0], [77.0, 13.0], [77.0, 12.0]]],
        },
        "outputs": {
            "analytic": {
                "path": "analytic.tif",
                "band_count": band_count,
                "dtype": "uint16",
                "scale": 0.0001,
                "offset": 0.0,
                "nodata": 0,
                "resolution": [23.5, 23.5],
                "crs": "EPSG:32643",
            },
            "mask": {
                "path": "mask.tif",
                "band_count": 1,
                "dtype": "uint8",
                "nodata": 0,
                "resolution": [23.5, 23.5],
                "crs": "EPSG:32643",
                "valid_classes": [1, 4],
                "excluded_classes": [0, 2, 3],
                "class_labels": {
                    "0": "nodata",
                    "1": "valid",
                    "2": "cloud",
                    "3": "shadow",
                    "4": "water",
                },
            },
        },
        # Coverage metrics at top level (prepare-manifest format; no "properties" wrapper
        # so that validate_manifest_metadata does not enter STAC-item mode and require
        # full datetime / eo:bands etc. that are only generated at catalog-load time).
        "akasha:metrics_provisional": True,
        "akasha:coverage_percent": 97.5,
    }
    m.update(extra)
    return m


# ---------------------------------------------------------------------------
# TASK-039 — verify-composite rejects non-optical-composite sources
# ---------------------------------------------------------------------------


class TestVerifyCompositeProfileGate:
    """verify-composite must reject non-optical-composite sources with an
    actionable error that names the correct alternative command."""

    def _run(self, source_id: str) -> tuple[int, str]:
        result = worker.main(["verify-composite", "--source", source_id])
        return result

    def test_rejects_eos04_sar_source(self, capsys):
        rc = self._run("eos-04-sar-mrs-l2b")
        assert rc == 1
        err = capsys.readouterr().err
        assert "optical_composite" in err
        assert "sar_backscatter" in err
        assert "verify-raster-product" in err
        assert "eos-04-sar-mrs-l2b" in err

    def test_rejects_nisar_sar_source(self, capsys):
        rc = self._run("nisar-ssar-beta-gcov")
        assert rc == 1
        err = capsys.readouterr().err
        assert "optical_composite" in err
        assert "sar_backscatter" in err
        assert "verify-raster-product" in err

    def test_rejects_sentinel1_sar_source(self, capsys):
        rc = self._run("sentinel-1-grd")
        assert rc == 1
        err = capsys.readouterr().err
        assert "optical_composite" in err
        assert "sar_backscatter" in err
        assert "verify-raster-product" in err

    def test_rejects_eos06_context_source(self, capsys):
        rc = self._run("eos-06-ocm-lac-ndvi-8day-360m")
        assert rc == 1
        err = capsys.readouterr().err
        assert "optical_composite" in err
        assert "precomputed_context" in err
        assert "verify-raster-product" in err

    def test_rejects_irs1c_archive_source(self, capsys):
        rc = self._run("irs-1c-liss3-archive")
        assert rc == 1
        err = capsys.readouterr().err
        assert "optical_composite" in err
        assert "archive_only" in err
        assert "verify-raster-product" in err

    def test_rejects_landsat7_archive_source(self, capsys):
        rc = self._run("landsat-7-c2-l2")
        assert rc == 1
        err = capsys.readouterr().err
        assert "optical_composite" in err
        assert "archive_only" in err
        assert "verify-raster-product" in err

    def test_error_message_names_source_id_and_its_profile(self, capsys):
        """The actionable error must name the rejected source and its profile."""
        self._run("eos-04-sar-mrs-l2b")
        err = capsys.readouterr().err
        assert "eos-04-sar-mrs-l2b" in err
        assert "sar_backscatter" in err


# ---------------------------------------------------------------------------
# TASK-040 — verify-raster-product: acceptance / rejection tests
# ---------------------------------------------------------------------------


class TestVerifyRasterProductSAR:
    """verify-raster-product must accept valid SAR manifests and reject
    wrong band counts or optical-index metadata (GEO-002)."""

    def test_accepts_valid_sar_manifest(self, tmp_path):
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(_sar_manifest("eos-04-sar-mrs-l2b")), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 0

    def test_accepts_nisar_sar_manifest_via_source_flag(self, tmp_path):
        manifest = _sar_manifest("nisar-ssar-beta-gcov")
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "nisar-ssar-beta-gcov",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 0

    def test_accepts_sar_manifest_via_profile_flag(self, tmp_path):
        """--profile sar_backscatter should work without --source."""
        manifest = {"outputs": {"backscatter": {"path": "backscatter.tif"}}}
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--profile",
                "sar_backscatter",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 0

    def test_rejects_sar_manifest_with_ndvi_geo002_violation(self, tmp_path, capsys):
        """GEO-002: SAR manifest that advertises NDVI must fail validation."""
        manifest = _sar_manifest(
            "eos-04-sar-mrs-l2b",
            statistics_roles=["NDVI", "NDMI"],
        )
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "GEO-002" in out
        assert "NDVI" in out

    def test_rejects_sar_manifest_with_msavi_geo002_violation(self, tmp_path, capsys):
        manifest = _sar_manifest("sentinel-1-grd", **{"allowed_statistics": ["MSAVI"]})
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "sentinel-1-grd",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "GEO-002" in out

    def test_rejects_missing_backscatter_asset(self, tmp_path, capsys):
        """SAR profile requires backscatter.tif; missing it must fail."""
        manifest = {
            "source_id": "eos-04-sar-mrs-l2b",
            "outputs": {
                "wrong_asset": {"path": "something.tif", "band_count": 1, "dtype": "float32"}
            },
        }
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "backscatter.tif" in out

    def test_rejects_eos04_manifest_missing_explicit_polarizations(self, tmp_path, capsys):
        manifest = _sar_manifest("eos-04-sar-mrs-l2b")
        manifest.pop("sar:polarizations")
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        out = capsys.readouterr().out
        assert "sar:polarizations" in out
        assert "VV or HH" in out

    def test_rejects_eos04_manifest_with_non_float32_backscatter(self, tmp_path, capsys):
        manifest = _sar_manifest("eos-04-sar-mrs-l2b")
        manifest["outputs"]["backscatter"]["dtype"] = "uint16"
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        assert "float32" in capsys.readouterr().out

    def test_rejects_eos04_manifest_missing_backscatter_dtype(self, tmp_path, capsys):
        manifest = _sar_manifest("eos-04-sar-mrs-l2b")
        manifest["outputs"]["backscatter"].pop("dtype")
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        out = capsys.readouterr().out
        assert "dtype" in out
        assert "float32" in out

    def test_rejects_eos04_manifest_missing_backscatter_band_count(self, tmp_path, capsys):
        manifest = _sar_manifest("eos-04-sar-mrs-l2b")
        manifest["outputs"]["backscatter"].pop("band_count")
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        assert "band_count" in capsys.readouterr().out

    def test_rejects_eos04_manifest_with_unknown_polarization_token(self, tmp_path, capsys):
        manifest = _sar_manifest("eos-04-sar-mrs-l2b")
        manifest["sar:polarizations"] = ["B1"]
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        out = capsys.readouterr().out
        assert "unsupported token" in out
        assert "B1" in out

    def test_fails_cleanly_when_no_source_no_profile(self, tmp_path, capsys):
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        rc = worker.main(["verify-raster-product", "--manifest", str(manifest_path)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "--source" in err or "--profile" in err


class TestVerifyRasterProductContext:
    """verify-raster-product accepts valid context/archive manifests."""

    def test_accepts_valid_context_manifest(self, tmp_path):
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(
            json.dumps(_context_manifest("eos-06-ocm-lac-ndvi-8day-360m")),
            encoding="utf-8",
        )
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-06-ocm-lac-ndvi-8day-360m",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 0

    def test_accepts_context_manifest_via_plan_doc_alias(self, tmp_path):
        """Plan-doc alias context_raster must resolve to precomputed_context."""
        manifest = {"outputs": {"context": {"path": "context.tif"}}}
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--profile",
                "context_raster",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 0

    def test_rejects_context_manifest_with_statistics_roles_geo003(self, tmp_path, capsys):
        """GEO-003: context manifest that advertises raw-band statistics must fail."""
        manifest = _context_manifest(
            "eos-06-ocm-lac-ndvi-8day-360m",
            statistics_roles=["NDVI"],
        )
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "eos-06-ocm-lac-ndvi-8day-360m",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "GEO-003" in out


class TestVerifyRasterProductLISS3:
    """verify-raster-product accepts valid LISS-3 manifests and rejects wrong
    band counts (TASK-040 / TASK-040A cross-check)."""

    def test_accepts_valid_liss3_manifest(self, tmp_path):
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(_liss3_manifest()), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 0

    def test_rejects_liss3_manifest_with_3_bands(self, tmp_path, capsys):
        """LISS-3 requires exactly 4 analytic bands; 3 must fail."""
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(_liss3_manifest(band_count=3)), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "band count" in out.lower() or "3" in out

    def test_rejects_liss3_manifest_with_9_bands(self, tmp_path, capsys):
        """LISS-3 requires exactly 4 analytic bands; Sentinel-2-like 9 must fail."""
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(_liss3_manifest(band_count=9)), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1

    def test_rejects_liss3_manifest_missing_mask_asset(self, tmp_path, capsys):
        """LISS-3 profile requires both analytic.tif AND mask.tif assets."""
        manifest = dict(_liss3_manifest())
        manifest["outputs"] = {
            "analytic": {
                "path": "analytic.tif",
                "band_count": 4,
                "dtype": "uint16",
            }
        }  # mask.tif missing
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "mask.tif" in out

    @pytest.mark.parametrize(
        ("field", "bad_value", "expected_text"),
        [
            ("dtype", "float32", "dtype"),
            ("scale", 0.00001, "scale"),
            ("offset", -0.1, "offset"),
            ("nodata", -9999, "nodata"),
        ],
    )
    def test_rejects_liss3_manifest_with_wrong_analytic_metadata(
        self, tmp_path, capsys, field, bad_value, expected_text
    ):
        """LISS-3 metadata validation must enforce release-blocking radiometry."""
        manifest = _liss3_manifest()
        manifest["outputs"]["analytic"][field] = bad_value
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        out = capsys.readouterr().out.lower()
        assert expected_text in out

    @pytest.mark.parametrize(
        ("field", "bad_value", "expected_text"),
        [
            ("valid_classes", [1], "valid"),
            ("excluded_classes", [0, 2], "excluded"),
            (
                "class_labels",
                {"0": "nodata", "1": "valid", "2": "cloud", "3": "shadow"},
                "class",
            ),
        ],
    )
    def test_rejects_liss3_manifest_with_wrong_mask_taxonomy(
        self, tmp_path, capsys, field, bad_value, expected_text
    ):
        """LISS-3 mask must stay Akasha threshold mask v1, not Sentinel SCL."""
        manifest = _liss3_manifest()
        manifest["outputs"]["mask"][field] = bad_value
        manifest_path = tmp_path / "prepare_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        rc = worker.main(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                str(manifest_path),
                "--metadata-only",
            ]
        )

        assert rc == 1
        out = capsys.readouterr().out.lower()
        assert expected_text in out


# ---------------------------------------------------------------------------
# Parser smoke tests for verify-raster-product CLI
# ---------------------------------------------------------------------------


class TestVerifyRasterProductParser:
    """Smoke-test that build_parser() produces correct Namespace for
    verify-raster-product sub-command flags."""

    def test_parse_source_flag(self):
        parser = worker.build_parser()
        args = parser.parse_args(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                "m.json",
            ]
        )
        assert args.source == "resourcesat-2a-liss3-boa"
        assert args.manifest == "m.json"
        assert args.profile is None

    def test_parse_profile_flag(self):
        parser = worker.build_parser()
        args = parser.parse_args(
            ["verify-raster-product", "--profile", "sar_backscatter", "--manifest", "s.json"]
        )
        assert args.profile == "sar_backscatter"
        assert args.source is None
        assert args.manifest == "s.json"

    def test_parse_both_source_and_profile(self):
        parser = worker.build_parser()
        args = parser.parse_args(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--profile",
                "sar_backscatter",
                "--manifest",
                "x.json",
            ]
        )
        assert args.source == "eos-04-sar-mrs-l2b"
        assert args.profile == "sar_backscatter"

    def test_parse_metadata_only_flag(self):
        parser = worker.build_parser()
        args = parser.parse_args(
            [
                "verify-raster-product",
                "--source",
                "eos-04-sar-mrs-l2b",
                "--manifest",
                "x.json",
                "--metadata-only",
            ]
        )
        assert args.metadata_only is True

    def test_metadata_only_defaults_to_false(self):
        parser = worker.build_parser()
        args = parser.parse_args(
            [
                "verify-raster-product",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--manifest",
                "m.json",
            ]
        )
        assert args.metadata_only is False

    def test_manifest_is_required(self):
        """--manifest is required for verify-raster-product."""
        parser = worker.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["verify-raster-product", "--source", "resourcesat-2a-liss3-boa"])

    def test_plan_doc_alias_is_accepted_as_profile(self):
        """Plan-doc aliases (context_raster, archive_optical, vhr_visual) must parse."""
        parser = worker.build_parser()
        for alias in ("context_raster", "archive_optical", "vhr_visual"):
            args = parser.parse_args(
                ["verify-raster-product", "--profile", alias, "--manifest", "m.json"]
            )
            assert args.profile == alias


# ---------------------------------------------------------------------------
# TASK-040A — ResourceSat LISS-3 invariant tests
# ---------------------------------------------------------------------------


class TestLISS3ModuleConstants:
    """Public module-level constants exported by validation_profiles must
    encode the exact REQ-017 / TASK-000E invariants."""

    def test_band_count_is_4(self):
        assert LISS3_BAND_COUNT == 4

    def test_band_roles_are_4_bands_in_correct_order(self):
        """Band order must be GREEN, RED, NIR, SWIR1 (BAND2, BAND3, BAND4, BAND5)."""
        assert LISS3_BAND_ROLES == ("GREEN", "RED", "NIR", "SWIR1")

    def test_band_roles_has_no_blue_band(self):
        assert "BLUE" not in LISS3_BAND_ROLES

    def test_scale_is_0_0001(self):
        assert LISS3_SCALE == 0.0001

    def test_offset_is_0_not_sentinel_minus_0_1(self):
        """Reflectance offset must be 0.0, NOT Sentinel-2's -0.1."""
        assert LISS3_OFFSET == 0.0

    def test_nodata_is_0(self):
        assert LISS3_NODATA == 0.0

    def test_mask_valid_classes_are_1_and_4(self):
        """Valid pixel classes: 1 (valid) and 4 (water)."""
        assert LISS3_MASK_VALID_CLASSES == frozenset({1, 4})

    def test_mask_excluded_classes_are_0_2_3(self):
        """Excluded classes: 0 (nodata), 2 (cloud), 3 (shadow)."""
        assert LISS3_MASK_EXCLUDED_CLASSES == frozenset({0, 2, 3})

    def test_valid_and_excluded_classes_are_disjoint(self):
        assert LISS3_MASK_VALID_CLASSES.isdisjoint(LISS3_MASK_EXCLUDED_CLASSES)

    def test_valid_and_excluded_classes_cover_all_5_classes(self):
        all_classes = LISS3_MASK_VALID_CLASSES | LISS3_MASK_EXCLUDED_CLASSES
        assert all_classes == {0, 1, 2, 3, 4}

    def test_fcc_display_roles_are_nir_red_green(self):
        """FCC = NIR/RED/GREEN; no true-colour roles, no blue."""
        assert LISS3_FCC_DISPLAY_ROLES == frozenset({"NIR", "RED", "GREEN"})

    def test_fcc_display_roles_excludes_blue(self):
        assert "BLUE" not in LISS3_FCC_DISPLAY_ROLES

    def test_supported_stats_include_4_indices(self):
        assert LISS3_SUPPORTED_STATS == frozenset({"NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"})

    def test_ndre_not_supported_no_red_edge_band(self):
        assert "NDRE" not in LISS3_SUPPORTED_STATS

    def test_reci_not_supported(self):
        assert "RECI" not in LISS3_SUPPORTED_STATS

    def test_expected_assets_requires_both_cogs(self):
        """Separate analytic and mask COG assets must both be required."""
        assert "analytic.tif" in LISS3_EXPECTED_ASSETS
        assert "mask.tif" in LISS3_EXPECTED_ASSETS

    def test_expected_assets_no_scl_asset(self):
        """No SCL (Sentinel-2 Scene Classification Layer) for LISS-3."""
        assert not any("scl" in a.lower() for a in LISS3_EXPECTED_ASSETS)


class TestLISS3ProfileSpec:
    """profile_for_source('resourcesat-2a-liss3-boa') must return a
    ValidationProfileSpec that encodes all LISS-3 invariants exactly."""

    @pytest.fixture(scope="class")
    def spec(self) -> ValidationProfileSpec:
        return profile_for_source("resourcesat-2a-liss3-boa")

    def test_profile_id_is_optical_composite(self, spec):
        assert spec.profile_id == "optical_composite"

    def test_band_count_is_4(self, spec):
        assert spec.band_count == 4

    def test_band_roles_correct_order(self, spec):
        assert spec.band_roles == ("GREEN", "RED", "NIR", "SWIR1")

    def test_scale_correct(self, spec):
        assert spec.scale == 0.0001

    def test_offset_is_zero_not_sentinel(self, spec):
        assert spec.offset == 0.0

    def test_nodata_is_zero(self, spec):
        assert spec.nodata == 0.0

    def test_mask_asset_is_separate_mask_tif(self, spec):
        """Mask must be a separate asset, not part of the analytic COG."""
        assert spec.mask_asset == "mask.tif"

    def test_mask_valid_classes(self, spec):
        assert spec.mask_valid_classes == frozenset({1, 4})

    def test_mask_excluded_classes(self, spec):
        assert spec.mask_excluded_classes == frozenset({0, 2, 3})

    def test_mask_class_labels_encode_akasha_threshold_mask_v1(self, spec):
        label_map = dict(spec.mask_class_labels)
        assert label_map[0] == "nodata"
        assert label_map[1] == "valid"
        assert label_map[2] == "cloud"
        assert label_map[3] == "shadow"
        assert label_map[4] == "water"

    def test_no_scl_mask_semantics(self, spec):
        """There is no SCL for LISS-3; mask_class_labels must not contain any
        Sentinel-2 SCL class names."""
        sentinel_scl_labels = {"dark_area_pixels", "saturated_or_defective", "vegetation"}
        actual_labels = {label for _, label in spec.mask_class_labels}
        assert actual_labels.isdisjoint(sentinel_scl_labels)

    def test_fcc_display_roles(self, spec):
        assert spec.allowed_display_roles == frozenset({"NIR", "RED", "GREEN"})

    def test_statistics_roles_include_ndvi_msavi_ndmi_ndwi(self, spec):
        assert spec.allowed_statistics_roles == frozenset(
            {"NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"}
        )

    def test_ndre_not_in_statistics_roles(self, spec):
        assert "NDRE" not in spec.allowed_statistics_roles

    def test_expected_assets_require_separate_analytic_and_mask(self, spec):
        assert "analytic.tif" in spec.expected_assets
        assert "mask.tif" in spec.expected_assets

    def test_overview_required(self, spec):
        assert spec.overview_required is True

    def test_stac_required_fields_include_akasha_composite(self, spec):
        """optical_composite STAC items must include akasha:composite field."""
        assert "akasha:composite" in spec.stac_required_fields

    def test_stac_required_fields_include_coverage_percent(self, spec):
        assert "akasha:coverage_percent" in spec.stac_required_fields

    def test_notes_mention_fcc_and_no_scl(self, spec):
        assert "FCC" in spec.notes
        assert "SCL" in spec.notes or "no SCL" in spec.notes or "threshold mask" in spec.notes


class TestLISS3CheckSourceStatisticsRole:
    """check_source_statistics_role must allow NDVI/MSAVI/NDMI/NDWI_GREEN_NIR
    and reject NDRE/RECI for LISS-3."""

    def test_allows_ndvi(self):
        check_source_statistics_role("resourcesat-2a-liss3-boa", "NDVI")

    def test_allows_msavi(self):
        check_source_statistics_role("resourcesat-2a-liss3-boa", "MSAVI")

    def test_allows_ndmi(self):
        check_source_statistics_role("resourcesat-2a-liss3-boa", "NDMI")

    def test_allows_ndwi_green_nir(self):
        check_source_statistics_role("resourcesat-2a-liss3-boa", "NDWI_GREEN_NIR")

    def test_rejects_ndre(self):
        with pytest.raises(ValueError, match="NDRE"):
            check_source_statistics_role("resourcesat-2a-liss3-boa", "NDRE")

    def test_rejects_reci(self):
        with pytest.raises(ValueError, match="RECI"):
            check_source_statistics_role("resourcesat-2a-liss3-boa", "RECI")


class TestLISS3STACItemDeterministicKeys:
    """build_stac_item_from_prepare_manifest must produce deterministic
    item IDs and S3 asset paths for LISS-3 composites."""

    def _build_item(self) -> dict:
        return catalog.build_stac_item_from_prepare_manifest(_liss3_manifest())

    def test_item_id_is_deterministic(self):
        """Calling the builder twice with the same manifest must yield the same ID."""
        item_a = self._build_item()
        item_b = self._build_item()
        assert item_a["id"] == item_b["id"]

    def test_item_id_format_for_composite(self):
        """LISS-3 composite item ID: {source_id}_composite_{aoi_id}_{date}."""
        item = self._build_item()
        assert item["id"] == "resourcesat-2a-liss3-boa_composite_bangalore-60km_2026-03-31"

    def test_analytic_href_uses_source_composite_aoi_date_layout(self):
        """analytic asset must use the canonical S3 composite key layout."""
        item = self._build_item()
        href = item["assets"]["analytic"]["href"]
        assert "resourcesat-2a-liss3-boa" in href
        assert "composite" in href
        assert "bangalore-60km" in href
        assert "2026-03-31" in href
        assert href.endswith("analytic.tif")

    def test_mask_href_is_separate_from_analytic(self):
        """mask COG must be a separate asset with its own href."""
        item = self._build_item()
        assert "mask" in item["assets"]
        mask_href = item["assets"]["mask"]["href"]
        analytic_href = item["assets"]["analytic"]["href"]
        assert mask_href != analytic_href
        assert mask_href.endswith("mask.tif")

    def test_analytic_and_mask_hrefs_share_same_directory(self):
        """Both assets must reside in the same composite directory prefix."""
        item = self._build_item()
        analytic_dir = item["assets"]["analytic"]["href"].rsplit("/", 1)[0]
        mask_dir = item["assets"]["mask"]["href"].rsplit("/", 1)[0]
        assert analytic_dir == mask_dir

    def test_no_scl_asset_in_liss3_item(self):
        """No Sentinel-2 SCL asset must appear in a LISS-3 STAC item."""
        item = self._build_item()
        assert "scl" not in item["assets"]

    def test_item_collection_matches_source_id(self):
        item = self._build_item()
        assert item["collection"] == "resourcesat-2a-liss3-boa"


class TestLISS3STACItemBandMetadata:
    """STAC item eo:bands must reflect the 4-band BOA band order and
    raster:bands scale/offset must match REQ-017."""

    def _build_item(self) -> dict:
        return catalog.build_stac_item_from_prepare_manifest(_liss3_manifest())

    def test_eo_bands_count_is_4(self):
        item = self._build_item()
        eo_bands = item["assets"]["analytic"]["eo:bands"]
        assert len(eo_bands) == 4

    def test_eo_bands_order_band2_band3_band4_band5(self):
        item = self._build_item()
        names = [b["name"] for b in item["assets"]["analytic"]["eo:bands"]]
        assert names == ["BAND2", "BAND3", "BAND4", "BAND5"]

    def test_raster_bands_count_matches_eo_bands(self):
        item = self._build_item()
        assert len(item["assets"]["analytic"]["raster:bands"]) == 4

    def test_raster_bands_scale_is_0_0001(self):
        item = self._build_item()
        for band in item["assets"]["analytic"]["raster:bands"]:
            assert band.get("scale") == pytest.approx(
                0.0001
            ), f"Expected scale 0.0001, got {band.get('scale')}"

    def test_raster_bands_offset_is_0_not_minus_0_1(self):
        """Reflectance offset for LISS-3 BOA is 0.0, NOT Sentinel-2's -0.1."""
        item = self._build_item()
        for band in item["assets"]["analytic"]["raster:bands"]:
            assert band.get("offset") == pytest.approx(
                0.0
            ), f"Expected offset 0.0 (not -0.1), got {band.get('offset')}"

    def test_mask_asset_has_1_raster_band(self):
        item = self._build_item()
        mask_bands = item["assets"]["mask"]["raster:bands"]
        assert len(mask_bands) == 1

    def test_item_properties_include_source_id(self):
        item = self._build_item()
        assert item["properties"]["akasha:source_id"] == "resourcesat-2a-liss3-boa"

    def test_item_properties_composite_flag_is_true(self):
        item = self._build_item()
        assert item["properties"]["akasha:composite"] is True

    def test_item_properties_band_role_mapping_has_swir1(self):
        item = self._build_item()
        mapping = item["properties"]["akasha:band_role_mapping"]
        assert mapping["GREEN"] == "BAND2"
        assert mapping["RED"] == "BAND3"
        assert mapping["NIR"] == "BAND4"
        assert mapping["SWIR1"] == "BAND5"

    def test_item_properties_mask_method_mentions_akasha_threshold_mask(self):
        item = self._build_item()
        mask_method = item["properties"].get("akasha:mask_method", "")
        assert "threshold" in mask_method.lower() or "akasha" in mask_method.lower()


class TestLISS3STACUpsertSemantics:
    """Verify that the STAC required fields for LISS-3 optical_composite
    profiles are present in the built item, enabling idempotent upsert."""

    def _build_item(self) -> dict:
        return catalog.build_stac_item_from_prepare_manifest(_liss3_manifest())

    def test_stac_version_present(self):
        item = self._build_item()
        assert item.get("stac_version") == "1.0.0"

    def test_datetime_present_in_properties(self):
        item = self._build_item()
        assert "datetime" in item["properties"]

    def test_source_id_present_in_properties(self):
        item = self._build_item()
        assert "akasha:source_id" in item["properties"]

    def test_composite_field_present(self):
        item = self._build_item()
        assert "akasha:composite" in item["properties"]

    def test_coverage_percent_present(self):
        item = self._build_item()
        assert "akasha:coverage_percent" in item["properties"]

    def test_item_has_id_and_collection_for_upsert_key(self):
        """pgSTAC upsert requires item["id"] and item["collection"] to be set."""
        item = self._build_item()
        assert item["id"]
        assert item["collection"]

    def test_two_builds_of_same_manifest_produce_same_upsert_key(self):
        """Determinism: re-ingesting the same manifest must produce the same
        item id so pgSTAC upsert is idempotent rather than creating duplicates."""
        item_a = self._build_item()
        item_b = self._build_item()
        assert (item_a["id"], item_a["collection"]) == (item_b["id"], item_b["collection"])


# ---------------------------------------------------------------------------
# Cross-profile invariant: validate_manifest_metadata API
# ---------------------------------------------------------------------------


class TestValidateManifestMetadataAPI:
    """Verify validate_manifest_metadata returns a typed ManifestValidationResult
    with the expected structure for each profile family."""

    def test_returns_manifest_validation_result_type(self):
        spec = get_validation_profile("sar_backscatter")
        result = validate_manifest_metadata(spec, _sar_manifest())
        assert isinstance(result, ManifestValidationResult)

    def test_ok_field_is_bool(self):
        spec = get_validation_profile("sar_backscatter")
        result = validate_manifest_metadata(spec, _sar_manifest())
        assert isinstance(result.ok, bool)

    def test_checks_is_tuple_of_strings(self):
        spec = get_validation_profile("sar_backscatter")
        result = validate_manifest_metadata(spec, _sar_manifest())
        assert isinstance(result.checks, tuple)
        assert all(isinstance(c, str) for c in result.checks)

    def test_problems_is_tuple_of_strings(self):
        spec = get_validation_profile("sar_backscatter")
        result = validate_manifest_metadata(spec, _sar_manifest())
        assert isinstance(result.problems, tuple)

    def test_detail_is_non_empty_string(self):
        spec = get_validation_profile("sar_backscatter")
        result = validate_manifest_metadata(spec, _sar_manifest())
        assert isinstance(result.detail, str) and result.detail

    def test_geo002_violation_ok_is_false(self):
        spec = profile_for_source("eos-04-sar-mrs-l2b")
        bad = _sar_manifest(statistics_roles=["NDVI"])
        result = validate_manifest_metadata(spec, bad, source_id="eos-04-sar-mrs-l2b")
        assert result.ok is False
        assert any("GEO-002" in p for p in result.problems)

    def test_geo003_violation_ok_is_false(self):
        spec = get_validation_profile("precomputed_context")
        bad = _context_manifest(statistics_roles=["NDVI"])
        result = validate_manifest_metadata(spec, bad)
        assert result.ok is False
        assert any("GEO-003" in p for p in result.problems)

    def test_source_id_mismatch_is_a_problem(self):
        spec = profile_for_source("eos-04-sar-mrs-l2b")
        manifest = _sar_manifest("nisar-ssar-beta-gcov")  # wrong source_id in manifest
        result = validate_manifest_metadata(spec, manifest, source_id="eos-04-sar-mrs-l2b")
        assert result.ok is False
        assert any("source_id" in p for p in result.problems)

    def test_liss3_stac_eo_bands_with_band_names_and_common_names_passes(self):
        """Real ResourceSat STAC uses name=BAND2..BAND5 and common_name roles."""
        spec = profile_for_source("resourcesat-2a-liss3-boa")
        manifest = _liss3_manifest()
        manifest["properties"] = {
            "datetime": "2026-03-31T00:00:00Z",
            "eo:bands": [
                {"name": "BAND2", "common_name": "green"},
                {"name": "BAND3", "common_name": "red"},
                {"name": "BAND4", "common_name": "nir"},
                {"name": "BAND5", "common_name": "swir16"},
            ],
            "raster:bands": [
                {"scale": 0.0001, "offset": 0.0},
                {"scale": 0.0001, "offset": 0.0},
                {"scale": 0.0001, "offset": 0.0},
                {"scale": 0.0001, "offset": 0.0},
            ],
            "akasha:source_id": "resourcesat-2a-liss3-boa",
            "akasha:composite": True,
            "akasha:coverage_percent": 97.5,
        }

        result = validate_manifest_metadata(
            spec,
            manifest,
            source_id="resourcesat-2a-liss3-boa",
        )

        assert result.ok is True
        assert any("eo:bands roles match spec" in check for check in result.checks)

    def test_liss3_stac_eo_bands_resolve_roles_from_band_role_mapping(self):
        """If common_name is absent, map BAND names through akasha:band_role_mapping."""
        spec = profile_for_source("resourcesat-2a-liss3-boa")
        manifest = _liss3_manifest()
        manifest["properties"] = {
            "datetime": "2026-03-31T00:00:00Z",
            "eo:bands": [
                {"name": "BAND2"},
                {"name": "BAND3"},
                {"name": "BAND4"},
                {"name": "BAND5"},
            ],
            "raster:bands": [
                {"scale": 0.0001, "offset": 0.0},
                {"scale": 0.0001, "offset": 0.0},
                {"scale": 0.0001, "offset": 0.0},
                {"scale": 0.0001, "offset": 0.0},
            ],
            "akasha:band_role_mapping": {
                "GREEN": "BAND2",
                "RED": "BAND3",
                "NIR": "BAND4",
                "SWIR1": "BAND5",
            },
            "akasha:source_id": "resourcesat-2a-liss3-boa",
            "akasha:composite": True,
            "akasha:coverage_percent": 97.5,
        }

        result = validate_manifest_metadata(
            spec,
            manifest,
            source_id="resourcesat-2a-liss3-boa",
        )

        assert result.ok is True
        assert any("eo:bands roles match spec" in check for check in result.checks)

    def test_get_validation_profile_rejects_unknown_key(self):
        with pytest.raises((ValueError, KeyError)):
            get_validation_profile("totally-unknown-profile-xyz")

    def test_plan_doc_aliases_resolve(self):
        for alias, expected_profile_id in (
            ("context_raster", "precomputed_context"),
            ("archive_optical", "archive_only"),
            ("vhr_visual", "visual_only"),
        ):
            spec = get_validation_profile(alias)
            assert spec.profile_id == expected_profile_id
