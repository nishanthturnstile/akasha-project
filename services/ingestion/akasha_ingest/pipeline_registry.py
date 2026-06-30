"""Source capability registry for staging ingestion pipelines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineSource:
    source_id: str
    provider: str
    collection_id: str
    prepare_script: str
    supports_search: bool
    supports_download: bool
    supports_composite: bool
    mvp_enabled: bool
    default_aoi_ids: tuple[str, ...]
    default_max_downloads: int
    default_min_coverage_percent: float
    output_profile: str
    notes: str
    supports_validate: bool = False
    manual_validation_enabled: bool = False


DEFAULT_AOI_IDS = ("bangalore-60km",)
DEFAULT_MAX_DOWNLOADS = 3
RESOURCESAT_PREPARE_SCRIPT = "prepare_resourcesat_liss3_boa_cogs.py"


PIPELINE_SOURCES: dict[str, PipelineSource] = {
    "resourcesat-2a-liss3-boa": PipelineSource(
        source_id="resourcesat-2a-liss3-boa",
        provider="bhoonidhi",
        collection_id="ResourceSat-2A_LISS3_BOA",
        prepare_script=RESOURCESAT_PREPARE_SCRIPT,
        supports_search=True,
        supports_download=True,
        supports_composite=True,
        mvp_enabled=True,
        default_aoi_ids=DEFAULT_AOI_IDS,
        default_max_downloads=DEFAULT_MAX_DOWNLOADS,
        default_min_coverage_percent=95.0,
        output_profile="resourcesat-liss3-boa",
        notes="MVP Bhoonidhi ResourceSat LISS-3 BOA optical source.",
    ),
    "resourcesat-2a-liss4-mx70-l2": PipelineSource(
        source_id="resourcesat-2a-liss4-mx70-l2",
        provider="bhoonidhi",
        collection_id="ResourceSat-2A_LISS4-MX70_L2",
        prepare_script=RESOURCESAT_PREPARE_SCRIPT,
        supports_search=True,
        supports_download=True,
        supports_composite=True,
        mvp_enabled=True,
        default_aoi_ids=DEFAULT_AOI_IDS,
        default_max_downloads=DEFAULT_MAX_DOWNLOADS,
        default_min_coverage_percent=10.0,
        output_profile="resourcesat-liss4-mx70-l2",
        notes="MVP Bhoonidhi ResourceSat LISS-4 narrow-swath optical source.",
    ),
    "resourcesat-2a-awifs-boa": PipelineSource(
        source_id="resourcesat-2a-awifs-boa",
        provider="bhoonidhi",
        collection_id="ResourceSat-2A_AWIFS_BOA",
        prepare_script=RESOURCESAT_PREPARE_SCRIPT,
        supports_search=True,
        supports_download=True,
        supports_composite=True,
        mvp_enabled=True,
        default_aoi_ids=DEFAULT_AOI_IDS,
        default_max_downloads=DEFAULT_MAX_DOWNLOADS,
        default_min_coverage_percent=95.0,
        output_profile="resourcesat-awifs-boa",
        notes="MVP Bhoonidhi ResourceSat AWiFS BOA optical source.",
    ),
    "sentinel-1-grd": PipelineSource(
        source_id="sentinel-1-grd",
        provider="cdse",
        collection_id="sentinel-1-grd",
        prepare_script="prepare_sentinel1_grd_cogs.py",
        supports_search=False,
        supports_download=False,
        supports_composite=False,
        mvp_enabled=False,
        default_aoi_ids=(),
        default_max_downloads=0,
        default_min_coverage_percent=0.0,
        output_profile="sentinel-1-grd",
        notes="Legacy SAR source retained for prepare-script dispatch compatibility.",
    ),
    "eos-04-sar-mrs-l2b": PipelineSource(
        source_id="eos-04-sar-mrs-l2b",
        provider="bhoonidhi",
        collection_id="EOS-04_SAR-MRS_L2B",
        prepare_script="prepare_eos04_sar_mrs_l2b_cogs.py",
        supports_search=True,
        supports_download=True,
        supports_composite=False,
        mvp_enabled=False,
        default_aoi_ids=(),
        default_max_downloads=0,
        default_min_coverage_percent=0.0,
        output_profile="eos-04-sar-mrs-l2b",
        notes=(
            "Gated Bhoonidhi SAR source enabled for explicit manual/staging validation only; "
            "display-only backscatter, no composite or default MVP exposure."
        ),
        supports_validate=True,
        manual_validation_enabled=True,
    ),
    "nisar-ssar-beta-gcov": PipelineSource(
        source_id="nisar-ssar-beta-gcov",
        provider="bhoonidhi",
        collection_id="NISAR_SSAR-Beta_GCOV",
        prepare_script="prepare_nisar_ssar_beta_gcov_cogs.py",
        supports_search=False,
        supports_download=False,
        supports_composite=False,
        mvp_enabled=False,
        default_aoi_ids=(),
        default_max_downloads=0,
        default_min_coverage_percent=0.0,
        output_profile="nisar-ssar-beta-gcov",
        notes="Gated Bhoonidhi SAR source retained for prepare-script dispatch compatibility.",
    ),
}

PREPARE_SCRIPTS: dict[str, str] = {
    source_id: source.prepare_script for source_id, source in PIPELINE_SOURCES.items()
}


def get_pipeline_source(source_id: str) -> PipelineSource:
    try:
        return PIPELINE_SOURCES[source_id]
    except KeyError as exc:
        raise KeyError(f"unsupported ingestion source: {source_id}") from exc


def supported_source_ids(provider: str | None = None) -> list[str]:
    return sorted(
        source.source_id
        for source in PIPELINE_SOURCES.values()
        if source.mvp_enabled and (provider is None or source.provider == provider)
    )


def prepare_script_name(source_id: str) -> str:
    return get_pipeline_source(source_id).prepare_script


def is_source_allowed(source_id: str, allowed_sources: set[str] | None) -> bool:
    source = get_pipeline_source(source_id)
    if allowed_sources is None:
        return source.mvp_enabled
    return source_id in allowed_sources and (source.mvp_enabled or source.manual_validation_enabled)
