"""Typed source-state registry for all 20 Akasha catalogue platforms.

Implements TASK-002 and TASK-003 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Separation of concerns
----------------------
- pipeline_registry.py  — legacy PipelineSource (search/download/prepare fields).
                          Preserved unchanged for backwards-compat during migration.
- source_registry.py    — typed SourceStateRow per REQ-004/REQ-005/REQ-018,
                          covering lifecycleState, scheduleState, capabilities,
                          productExposure, commercialState, aoiScope, validationState,
                          readinessReasons, validationProfile, cadence, hostPool, ownedBy.

A catalogue platform may map to multiple source rows via explicit productVariant splits
(e.g. resourcesat-2a -> liss3-boa / liss4-mx70-l2 / awifs-boa). Every row traces
back to exactly one catalogSlug unless it is explicitly marked internal legacy.

Fail-closed validation
----------------------
_validate_row() rejects contradictory combinations at registry load time:
  - commercial_blocked + order capability
  - archive_only schedule cadence + ROUTINE state
  - background_only schedule state + product_active exposure
  - out_of_aoi / reference_only aoi_scope + product_active exposure
  - executable row with missing catalogSlug
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Enums — state taxonomy (REQ-005)
# ---------------------------------------------------------------------------


class LifecycleState(StrEnum):
    """Tracks where a source is in its readiness lifecycle."""

    CATALOGUED = "catalogued"
    PROVIDER_CONFIGURED = "provider_configured"
    SEARCH_ENABLED = "search_enabled"
    DOWNLOAD_ENABLED = "download_enabled"
    ORDER_ENABLED = "order_enabled"
    PREPARE_ENABLED = "prepare_enabled"
    VALIDATE_ENABLED = "validate_enabled"


class ScheduleState(StrEnum):
    """Controls whether the scheduler may run routine jobs for this source."""

    DISABLED = "disabled"
    DRY_RUN = "dry_run"
    BACKGROUND_ONLY = "background_only"
    ROUTINE = "routine"
    ARCHIVE_ONLY = "archive_only"
    MANUAL_ONLY = "manual_only"


class Capability(StrEnum):
    """Individual capabilities a source exposes to the scheduler."""

    SEARCH = "search_enabled"
    DOWNLOAD = "download_enabled"
    ORDER = "order_enabled"
    POLL_ORDER = "poll_order"
    CANCEL_ORDER = "cancel_order"
    PREPARE = "prepare_enabled"
    COMPOSITE = "composite"
    VALIDATE = "validate_enabled"
    STATISTICS = "statistics"
    DISPLAY_TILES = "display_tiles"


class ProductExposure(StrEnum):
    """Controls what users/BFF can access from this source."""

    HIDDEN = "hidden"
    BACKGROUND_ONLY = "background_only"
    PRODUCT_ACTIVE = "product_active"
    REFERENCE_ONLY = "reference_only"


class CommercialState(StrEnum):
    """Whether paid/order APIs are commercially approved for this source."""

    COMMERCIAL_BLOCKED = "commercial_blocked"
    APPROVED = "approved"
    FREE = "free"


class AoiScope(StrEnum):
    """AOI applicability for this source."""

    IN_AOI = "in_aoi"
    PARTIAL_AOI = "partial_aoi"
    OUT_OF_AOI = "out_of_aoi"
    REFERENCE_ONLY = "reference_only"


class ValidationState(StrEnum):
    """Current validation status for this source's pipeline."""

    UNVALIDATED = "unvalidated"
    VALIDATION_PENDING = "validation_pending"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"


class ValidationProfile(StrEnum):
    """Which validation profile applies to this source's raster products (REQ-008)."""

    OPTICAL_COMPOSITE = "optical_composite"
    OPTICAL_SCENE = "optical_scene"
    SAR_BACKSCATTER = "sar_backscatter"
    PRECOMPUTED_CONTEXT = "precomputed_context"
    ARCHIVE_ONLY = "archive_only"
    VISUAL_ONLY = "visual_only"


class CadenceClass(StrEnum):
    """Nominal scheduling cadence class (REQ-009)."""

    MULTIPLE_PER_DAY = "multiple_per_day"
    DAILY = "daily"
    TWO_TO_FIVE_DAYS = "2_to_5_days"
    FIVE_TO_TEN_DAYS = "5_to_10_days"
    TEN_TO_TWENTY_DAYS = "10_to_20_days"
    GT_TWENTY_DAYS = "gt_20_days"
    ARCHIVE_ON_DEMAND = "archive_on_demand"
    REFERENCE = "reference"


class HostPool(StrEnum):
    """Which host/runtime may execute provider calls for this source (SRC-001)."""

    STAGING_BHOONIDHI = "staging_bhoonidhi"
    APPROVED_WORKER = "approved_worker"
    MANUAL_ONLY = "manual_only"
    NONE = "none"


class OwnedBy(StrEnum):
    """Which scheduling mechanism currently owns this source/AOI (OPS-010)."""

    LEGACY_TIMER = "legacy_timer"
    SCHEDULER_DRY_RUN = "scheduler_dry_run"
    SCHEDULER_ACTIVE = "scheduler_active"
    MANUAL_ONLY = "manual_only"


# ---------------------------------------------------------------------------
# Source state row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceStateRow:
    """Full scheduler source-state row.  One row per instrument/product variant.

    Required fields map to the catalogue-slug → source mapping contract in
    docs/reference/satellite-catalog.md §8 and REQ-018.
    """

    # Catalogue linkage (REQ-018)
    catalog_slug: str
    catalog_platform: str
    source_id: str
    provider_adapter: str
    product_family: str
    instrument_mode: str
    product_variant: str
    analysis_level: str

    # Scheduler/source state (REQ-005)
    lifecycle_state: LifecycleState
    schedule_state: ScheduleState
    capabilities: frozenset[Capability]
    product_exposure: ProductExposure
    commercial_state: CommercialState
    aoi_scope: AoiScope
    validation_state: ValidationState
    readiness_reasons: tuple[str, ...]

    # Validation and scheduling metadata (REQ-008, REQ-009)
    validation_profile: ValidationProfile
    cadence: CadenceClass
    host_pool: HostPool
    owned_by: OwnedBy

    # Optional per-source scheduling overrides
    default_aoi_ids: tuple[str, ...] = ()
    max_downloads: int = 0
    min_coverage_percent: float = 0.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Fail-closed validation helpers
# ---------------------------------------------------------------------------

_ROUTINE_SCHEDULE_STATES: frozenset[ScheduleState] = frozenset(
    {ScheduleState.ROUTINE, ScheduleState.BACKGROUND_ONLY}
)

_EXECUTABLE_STATES: frozenset[ScheduleState] = frozenset(
    {
        ScheduleState.ROUTINE,
        ScheduleState.BACKGROUND_ONLY,
        ScheduleState.DRY_RUN,
        ScheduleState.MANUAL_ONLY,
        ScheduleState.ARCHIVE_ONLY,
    }
)


def _validate_row(row: SourceStateRow) -> None:
    """Raise ValueError for any contradictory state combination.

    Fail-closed: invalid registry entries are rejected at module load time
    so misconfigured sources never silently become executable.
    """
    sid = row.source_id

    # commercial_blocked + order capability
    if row.commercial_state == CommercialState.COMMERCIAL_BLOCKED:
        if Capability.ORDER in row.capabilities:
            raise ValueError(
                f"source {sid!r}: ORDER capability requires commercial_state != commercial_blocked "
                f"(SEC-004/SRC-005)"
            )
        if Capability.POLL_ORDER in row.capabilities or Capability.CANCEL_ORDER in row.capabilities:
            raise ValueError(
                f"source {sid!r}: POLL_ORDER/CANCEL_ORDER require "
                f"commercial_state != commercial_blocked (SEC-004)"
            )

    # archive_only cadence + routine schedule state
    if row.cadence == CadenceClass.ARCHIVE_ON_DEMAND:
        if row.schedule_state in _ROUTINE_SCHEDULE_STATES:
            raise ValueError(
                f"source {sid!r}: archive_on_demand cadence cannot have schedule_state "
                f"{row.schedule_state.value!r}; use archive_only or manual_only (SRC-007)"
            )

    # archive_only schedule state + non-archive cadence
    if row.schedule_state == ScheduleState.ARCHIVE_ONLY:
        if row.cadence != CadenceClass.ARCHIVE_ON_DEMAND:
            raise ValueError(
                f"source {sid!r}: archive_only schedule_state requires "
                f"archive_on_demand cadence (SRC-007)"
            )

    # background_only schedule state + product_active exposure
    if row.schedule_state == ScheduleState.BACKGROUND_ONLY:
        if row.product_exposure == ProductExposure.PRODUCT_ACTIVE:
            raise ValueError(
                f"source {sid!r}: background_only scheduleState is incompatible with "
                f"product_active exposure (REQ-012)"
            )

    # disabled schedule state + background-only exposure
    if row.schedule_state == ScheduleState.DISABLED:
        if row.product_exposure == ProductExposure.BACKGROUND_ONLY:
            raise ValueError(
                f"source {sid!r}: disabled schedule_state cannot have "
                f"background_only product exposure"
            )

    # out_of_aoi / reference_only aoi_scope + product_active exposure
    if row.aoi_scope in (AoiScope.OUT_OF_AOI, AoiScope.REFERENCE_ONLY):
        if row.product_exposure == ProductExposure.PRODUCT_ACTIVE:
            raise ValueError(
                f"source {sid!r}: aoi_scope={row.aoi_scope.value!r} cannot have "
                f"product_active exposure (SRC-006)"
            )

    # validation gate: product_active requires validation_passed
    if row.product_exposure == ProductExposure.PRODUCT_ACTIVE:
        if row.validation_state != ValidationState.VALIDATION_PASSED:
            raise ValueError(
                f"source {sid!r}: product_active exposure requires "
                f"validation_state=validation_passed"
            )

    # routine schedule cannot run unvalidated sources
    if row.schedule_state == ScheduleState.ROUTINE:
        if row.validation_state == ValidationState.UNVALIDATED:
            raise ValueError(
                f"source {sid!r}: routine schedule_state requires validation before scheduling"
            )

    # executable row missing catalog_slug
    if row.schedule_state in _EXECUTABLE_STATES:
        if not row.catalog_slug:
            raise ValueError(
                f"source {sid!r}: executable/scheduled rows must have a non-empty "
                f"catalog_slug (REQ-018)"
            )


# ---------------------------------------------------------------------------
# Registry — all 20 catalogue slugs
# ---------------------------------------------------------------------------

_DEFAULT_AOI_IDS: tuple[str, ...] = ("bangalore-60km",)

# Capabilities shorthands
_SEARCH_ONLY = frozenset({Capability.SEARCH})
_SEARCH_DOWNLOAD = frozenset({Capability.SEARCH, Capability.DOWNLOAD})
_SEARCH_DOWNLOAD_PREPARE = frozenset(
    {Capability.SEARCH, Capability.DOWNLOAD, Capability.PREPARE}
)
_FULL_OPTICAL = frozenset(
    {
        Capability.SEARCH,
        Capability.DOWNLOAD,
        Capability.PREPARE,
        Capability.COMPOSITE,
        Capability.VALIDATE,
        Capability.STATISTICS,
        Capability.DISPLAY_TILES,
    }
)
_COMMERCIAL_ORDER = frozenset(
    {
        Capability.SEARCH,
        Capability.DOWNLOAD,
        Capability.ORDER,
        Capability.POLL_ORDER,
        Capability.CANCEL_ORDER,
    }
)
_EMPTY_CAPS: frozenset[Capability] = frozenset()


def _row(**kwargs) -> SourceStateRow:
    """Construct and validate a SourceStateRow, raising on contradictions."""
    r = SourceStateRow(**kwargs)
    _validate_row(r)
    return r


# fmt: off
SOURCE_REGISTRY: dict[str, SourceStateRow] = {}

def _register(*rows: SourceStateRow) -> None:
    for r in rows:
        if r.source_id in SOURCE_REGISTRY:
            raise ValueError(f"duplicate source_id in SOURCE_REGISTRY: {r.source_id!r}")
        SOURCE_REGISTRY[r.source_id] = r


# ---------------------------------------------------------------------------
# 1. ResourceSat-2A (ISRO/Bhoonidhi) — 3 source rows — the production path
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="resourcesat-2a",
        catalog_platform="ResourceSat-2A",
        source_id="resourcesat-2a-liss3-boa",
        provider_adapter="bhoonidhi",
        product_family="optical_multispectral",
        instrument_mode="LISS-3",
        product_variant="BOA",
        analysis_level="L2",
        lifecycle_state=LifecycleState.VALIDATE_ENABLED,
        schedule_state=ScheduleState.ROUTINE,
        capabilities=_FULL_OPTICAL,
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.VALIDATION_PASSED,
        readiness_reasons=(),
        validation_profile=ValidationProfile.OPTICAL_COMPOSITE,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.LEGACY_TIMER,
        default_aoi_ids=_DEFAULT_AOI_IDS,
        max_downloads=3,
        min_coverage_percent=95.0,
        notes="MVP production source. 4 bands [BAND2 Green, BAND3 Red, BAND4 NIR, BAND5 SWIR1]; "
              "FCC display NIR/RED/GREEN; reflectance scale 0.0001, offset 0.0; "
              "Akasha threshold mask v1; no SCL.",
    ),
    _row(
        catalog_slug="resourcesat-2a",
        catalog_platform="ResourceSat-2A",
        source_id="resourcesat-2a-liss4-mx70-l2",
        provider_adapter="bhoonidhi",
        product_family="optical_multispectral",
        instrument_mode="LISS-4",
        product_variant="MX70-L2",
        analysis_level="L2",
        lifecycle_state=LifecycleState.VALIDATE_ENABLED,
        schedule_state=ScheduleState.ROUTINE,
        capabilities=_FULL_OPTICAL,
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.VALIDATION_PASSED,
        readiness_reasons=(),
        validation_profile=ValidationProfile.OPTICAL_SCENE,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.LEGACY_TIMER,
        default_aoi_ids=_DEFAULT_AOI_IDS,
        max_downloads=3,
        min_coverage_percent=10.0,
        notes="Active high-resolution field enhancement. Narrow-swath; "
              "field-intersection fallback semantics; 70 km swath at 5 m.",
    ),
    _row(
        catalog_slug="resourcesat-2a",
        catalog_platform="ResourceSat-2A",
        source_id="resourcesat-2a-awifs-boa",
        provider_adapter="bhoonidhi",
        product_family="optical_multispectral",
        instrument_mode="AWiFS",
        product_variant="BOA",
        analysis_level="L2",
        lifecycle_state=LifecycleState.VALIDATE_ENABLED,
        schedule_state=ScheduleState.BACKGROUND_ONLY,
        capabilities=_FULL_OPTICAL,
        product_exposure=ProductExposure.BACKGROUND_ONLY,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.VALIDATION_FAILED,
        readiness_reasons=(
            "AWiFS composite coverage reached only 62.98% against 95% threshold "
            "(akasha-awifs-validation-2026-06-23). Product exposure remains background_only "
            "until a validated composite meets the accepted coverage threshold.",
        ),
        validation_profile=ValidationProfile.OPTICAL_COMPOSITE,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.LEGACY_TIMER,
        default_aoi_ids=_DEFAULT_AOI_IDS,
        max_downloads=3,
        min_coverage_percent=95.0,
        notes="Background ingestion allowed; product exposure gated until coverage validation. "
              "REQ-012: search/download/prepare may run while product is blocked.",
    ),
)

# ---------------------------------------------------------------------------
# 2. Sentinel-2 (ESA/CDSE) — gated
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="sentinel-2",
        catalog_platform="Sentinel-2",
        source_id="sentinel-2-l2a",
        provider_adapter="cdse",
        product_family="optical_multispectral",
        instrument_mode="MSI",
        product_variant="L2A",
        analysis_level="L2A",
        lifecycle_state=LifecycleState.PROVIDER_CONFIGURED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD_PREPARE,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "CDSE STAC/OData integration and OAuth2/Keycloak auth not yet validated "
            "for Akasha pipeline.",
            "Optical composite validation profile requires end-to-end parity test "
            "before product_active.",
        ),
        validation_profile=ValidationProfile.OPTICAL_COMPOSITE,
        cadence=CadenceClass.TWO_TO_FIVE_DAYS,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="Legacy Sentinel-2 support retained as opt-in. Red-edge bands (NDRE) available; "
              "10 m at 290 km swath. Gated until CDSE adapter validation passes.",
    ),
)

# ---------------------------------------------------------------------------
# 3. Sentinel-1 (ESA/CDSE) — gated SAR
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="sentinel-1",
        catalog_platform="Sentinel-1",
        source_id="sentinel-1-grd",
        provider_adapter="cdse",
        product_family="sar",
        instrument_mode="IW",
        product_variant="GRD",
        analysis_level="L1-GRD",
        lifecycle_state=LifecycleState.PROVIDER_CONFIGURED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD_PREPARE,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "SAR backscatter validation profile not yet implemented for Akasha pipeline.",
            "No optical vegetation indices; SAR-specific analytics required.",
            "GEO-002: SAR sources must not advertise optical indices.",
        ),
        validation_profile=ValidationProfile.SAR_BACKSCATTER,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="C-band SAR; cloud-piercing; 20 m / 250 km swath. "
              "Retained for prepare-script dispatch compatibility (legacy).",
    ),
)

# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="landsat-8",
        catalog_platform="Landsat 8",
        source_id="landsat-8-c2-l2",
        provider_adapter="usgs",
        product_family="optical_multispectral",
        instrument_mode="OLI+TIRS",
        product_variant="Collection-2-L2",
        analysis_level="L2SP",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "USGS Earth Explorer / STAC+COG adapter not yet implemented.",
            "Cloud-native COG path preferred; requires earthdata token handling.",
        ),
        validation_profile=ValidationProfile.OPTICAL_COMPOSITE,
        cadence=CadenceClass.TEN_TO_TWENTY_DAYS,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="15–30 m; 16-day revisit; 185 km swath. Thermal bands for stress. "
              "Collection 2 L2 cloud-native STAC+COG preferred (SRC-003).",
    ),
)

# ---------------------------------------------------------------------------
# 5. Landsat 9 (NASA/USGS) — gated
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="landsat-9",
        catalog_platform="Landsat 9",
        source_id="landsat-9-c2-l2",
        provider_adapter="usgs",
        product_family="optical_multispectral",
        instrument_mode="OLI-2+TIRS-2",
        product_variant="Collection-2-L2",
        analysis_level="L2SP",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "USGS STAC+COG adapter not yet implemented.",
            "Effective 8-day revisit when paired with Landsat 8; "
            "multi-source merge not yet designed.",
        ),
        validation_profile=ValidationProfile.OPTICAL_COMPOSITE,
        cadence=CadenceClass.TEN_TO_TWENTY_DAYS,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="15 m Pan / 30 m multispectral; 16-day revisit; 185 km swath.",
    ),
)

# ---------------------------------------------------------------------------
# 6. MODIS Terra/Aqua (NASA Earthdata) — regional context only
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="modis",
        catalog_platform="MODIS (Terra / Aqua)",
        source_id="modis-13q1-061",
        provider_adapter="earthdata",
        product_family="optical_multispectral",
        instrument_mode="MODIS",
        product_variant="MOD13Q1-061",
        analysis_level="L3",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "GEO-003: precomputed context NDVI; not a raw-reflectance field-analytics source.",
            "Earthdata token adapter not yet implemented.",
            "Context raster validation profile required before any product exposure.",
        ),
        validation_profile=ValidationProfile.PRECOMPUTED_CONTEXT,
        cadence=CadenceClass.DAILY,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="250 m; daily; 2330 km swath. Regional context only — not field statistics. "
              "Precomputed 16-day NDVI composite (MOD13Q1) is the intended product.",
    ),
)

# ---------------------------------------------------------------------------
# 7. Cartosat-3 (ISRO) — VHR manual placeholder
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="cartosat-3",
        catalog_platform="Cartosat-3",
        source_id="cartosat-3-gated",
        provider_adapter="vendor",
        product_family="optical_vhr",
        instrument_mode="Pan+MS",
        product_variant="L2",
        analysis_level="L2",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.MANUAL_ONLY,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "No programmatic Bhoonidhi catalog path for Cartosat-3 yet confirmed.",
            "GE entities may access via Bhoonidhi declaration; NGE requires NSIL licence.",
            "VHR visual validation profile required before any analytics use.",
        ),
        validation_profile=ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        host_pool=HostPool.MANUAL_ONLY,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="0.25 m pan; 4–5 day revisit; 16 km swath. "
              "Manual/VHR context placeholder. Indian Space Policy 2023 licensing applies.",
    ),
)

# ---------------------------------------------------------------------------
# 8. EOS-04 / RISAT (ISRO/Bhoonidhi) — gated SAR
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="eos-04-risat",
        catalog_platform="EOS-04 (RISAT)",
        source_id="eos-04-sar-mrs-l2b",
        provider_adapter="bhoonidhi",
        product_family="sar",
        instrument_mode="MRS",
        product_variant="L2B",
        analysis_level="L2B",
        lifecycle_state=LifecycleState.PROVIDER_CONFIGURED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD_PREPARE,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "SAR backscatter validation profile not yet implemented.",
            "GEO-002: SAR sources must not advertise optical vegetation indices.",
            "MRS/CRS modes only; FRS-1 fine modes are not freely available.",
        ),
        validation_profile=ValidationProfile.SAR_BACKSCATTER,
        cadence=CadenceClass.TEN_TO_TWENTY_DAYS,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="C-band SAR; 1–50 m modes; 12-day revisit. "
              "Retained for prepare-script dispatch compatibility. "
              "MRS/CRS modes free via NRSC; FRS-1 not free.",
    ),
)

# ---------------------------------------------------------------------------
# 9. EOS-06 / OceanSat-3 (ISRO/Bhoonidhi) — regional context
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="eos-06-oceansat-3",
        catalog_platform="EOS-06 (OceanSat-3)",
        source_id="eos-06-ocm-lac-ndvi-8day-360m",
        provider_adapter="bhoonidhi",
        product_family="optical_multispectral",
        instrument_mode="OCM",
        product_variant="LAC-NDVI-8day-360m",
        analysis_level="L3",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "GEO-003: precomputed NDVI context product; not raw-reflectance field analytics.",
            "Context raster validation profile required before product exposure.",
        ),
        validation_profile=ValidationProfile.PRECOMPUTED_CONTEXT,
        cadence=CadenceClass.TWO_TO_FIVE_DAYS,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="360 m; 2-day revisit; 1440 km swath. Regional context only. "
              "8-day NDVI composite via OCM LAC product.",
    ),
)

# ---------------------------------------------------------------------------
# 10. ALOS-2 / PALSAR-2 (JAXA) — 2 rows: commercial scenes + free mosaic
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="alos-2-palsar-2",
        catalog_platform="ALOS-2 (PALSAR-2)",
        source_id="alos2-palsar2",
        provider_adapter="jaxa",
        product_family="sar",
        instrument_mode="PALSAR-2",
        product_variant="SLC-CEOS",
        analysis_level="L1.5",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "JAXA/reseller-specific auth and order API not yet implemented.",
            "Commercial scenes require paid subscription; SRC-005 blocks order by default.",
            "GEO-002: L-band SAR; no optical vegetation indices.",
        ),
        validation_profile=ValidationProfile.SAR_BACKSCATTER,
        cadence=CadenceClass.TEN_TO_TWENTY_DAYS,
        host_pool=HostPool.MANUAL_ONLY,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="L-band SAR; 3–10 m; 14-day revisit. Commercial scenes blocked. "
              "Canopy penetration for biomass/soil moisture.",
    ),
    _row(
        catalog_slug="alos-2-palsar-2",
        catalog_platform="ALOS-2 (PALSAR-2)",
        source_id="alos2-mosaic-25m",
        provider_adapter="jaxa",
        product_family="sar",
        instrument_mode="PALSAR-2",
        product_variant="Annual-Mosaic-25m",
        analysis_level="L2.2",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "JAXA global SAR mosaic fetch adapter not yet implemented.",
            "SAR backscatter validation profile required before any product exposure.",
            "Context/regional use only; GEO-003 applies if used as precomputed product.",
        ),
        validation_profile=ValidationProfile.SAR_BACKSCATTER,
        cadence=CadenceClass.ARCHIVE_ON_DEMAND,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="Annual 25 m global SAR mosaic; free via JAXA PALSAR mosaic portal. "
              "Regional SAR context use; fetch-only, no commercial risk.",
    ),
)

# ---------------------------------------------------------------------------
# 11. SuperView NEO-1 (SIIS) — commercial blocked
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="superview-neo-1",
        catalog_platform="SuperView NEO-1",
        source_id="superview-neo-1",
        provider_adapter="vendor",
        product_family="optical_vhr",
        instrument_mode="Pan+MS",
        product_variant="BOA",
        analysis_level="L2",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "No vendor contract or quota in place (SRC-005).",
            "Paid tasking disabled by default; requires commercial readiness record (SEC-007).",
        ),
        validation_profile=ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.MULTIPLE_PER_DAY,
        host_pool=HostPool.NONE,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="0.3 m; daily; SIIS China commercial platform.",
    ),
)

# ---------------------------------------------------------------------------
# 12. PlanetScope (Planet Labs) — commercial blocked
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="planetscope",
        catalog_platform="PlanetScope",
        source_id="planetscope",
        provider_adapter="planet",
        product_family="optical_multispectral",
        instrument_mode="PS2",
        product_variant="SR",
        analysis_level="L3A",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_ONLY,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "No Planet API subscription or quota in place (SRC-005).",
            "Search-only until contract/quota/readiness is signed off.",
            "Paid download/order disabled by default; requires commercial readiness "
            "record (SEC-007).",
        ),
        validation_profile=ValidationProfile.OPTICAL_COMPOSITE,
        cadence=CadenceClass.DAILY,
        host_pool=HostPool.NONE,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="3–5 m; daily; B/G/R/RE/NIR (red-edge). "
              "High-cadence NDVI gold standard for smallholder crops.",
    ),
)

# ---------------------------------------------------------------------------
# 13. SkySat (Planet Labs) — commercial blocked
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="skysat",
        catalog_platform="SkySat",
        source_id="skysat",
        provider_adapter="planet",
        product_family="optical_vhr",
        instrument_mode="SkySat",
        product_variant="Collect",
        analysis_level="L1B",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "No Planet API subscription or quota in place (SRC-005).",
            "Paid task/order disabled by default; requires commercial readiness record (SEC-007).",
        ),
        validation_profile=ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.MULTIPLE_PER_DAY,
        host_pool=HostPool.NONE,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="0.5 m; multiple per day; Planet Labs commercial.",
    ),
)

# ---------------------------------------------------------------------------
# 14. BlackSky Gen 3 (BlackSky) — commercial blocked
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="blacksky-gen-3",
        catalog_platform="BlackSky Gen 3",
        source_id="blacksky-gen-3",
        provider_adapter="vendor",
        product_family="optical_vhr",
        instrument_mode="Gen3",
        product_variant="AnalyticSR",
        analysis_level="L2",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "No BlackSky vendor contract or quota in place (SRC-005).",
            "Paid task/order disabled by default; requires commercial readiness record (SEC-007).",
        ),
        validation_profile=ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.MULTIPLE_PER_DAY,
        host_pool=HostPool.NONE,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="0.35 m; 15× per day; 5 km swath. Disaster-response sub-hourly.",
    ),
)

# ---------------------------------------------------------------------------
# 15. KOMPSAT-3A (KARI/SIIS) — commercial blocked
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="kompsat-3a",
        catalog_platform="KOMPSAT-3A",
        source_id="kompsat-3a",
        provider_adapter="vendor",
        product_family="optical_vhr",
        instrument_mode="AEISS-A",
        product_variant="PAN+MS",
        analysis_level="L2G",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "No KARI/SIIS vendor contract or quota in place (SRC-005).",
            "Paid task/order disabled by default; requires commercial readiness record (SEC-007).",
            "MWIR thermal payload may require additional export licensing.",
        ),
        validation_profile=ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.TWO_TO_FIVE_DAYS,
        host_pool=HostPool.NONE,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="0.4 m; 1.5-day revisit; 13 km swath. MWIR thermal-stress payload.",
    ),
)

# ---------------------------------------------------------------------------
# 16. Landsat 7 (NASA/USGS) — archive only
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="landsat-7",
        catalog_platform="Landsat 7",
        source_id="landsat-7-c2-l2",
        provider_adapter="usgs",
        product_family="optical_multispectral",
        instrument_mode="ETM+",
        product_variant="Collection-2-L2",
        analysis_level="L2SP",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.ARCHIVE_ONLY,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "Decommissioned 2024; archive-only/on-demand. "
            "Not a routine current-monitoring source (SRC-007).",
            "USGS STAC+COG adapter not yet implemented.",
            "SLC-off scan line failure (post-2003) reduces valid pixel coverage.",
        ),
        validation_profile=ValidationProfile.ARCHIVE_ONLY,
        cadence=CadenceClass.ARCHIVE_ON_DEMAND,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="30 m; 1999–2024; SLC-off gap after 2003. Historical baseline only.",
    ),
)

# ---------------------------------------------------------------------------
# 17. Landsat 5 (NASA/USGS) — archive only
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="landsat-5",
        catalog_platform="Landsat 5",
        source_id="landsat-5-c2-l2",
        provider_adapter="usgs",
        product_family="optical_multispectral",
        instrument_mode="TM",
        product_variant="Collection-2-L2",
        analysis_level="L2SP",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.ARCHIVE_ONLY,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "Decommissioned 2013; archive-only/on-demand. "
            "Not a routine current-monitoring source (SRC-007).",
            "USGS STAC+COG adapter not yet implemented.",
        ),
        validation_profile=ValidationProfile.ARCHIVE_ONLY,
        cadence=CadenceClass.ARCHIVE_ON_DEMAND,
        host_pool=HostPool.APPROVED_WORKER,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="30–60 m; 1984–2013. 40-year historical archive for decadal analysis.",
    ),
)

# ---------------------------------------------------------------------------
# 18. IRS-1C (ISRO) — archive only
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="irs-1c",
        catalog_platform="IRS-1C",
        source_id="irs-1c-liss3-archive",
        provider_adapter="bhoonidhi",
        product_family="optical_multispectral",
        instrument_mode="LISS-3",
        product_variant="Archive",
        analysis_level="L2",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.ARCHIVE_ONLY,
        capabilities=_SEARCH_DOWNLOAD,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "Decommissioned 2007; archive-only/on-demand. "
            "Not a routine current-monitoring source (SRC-007).",
            "Archive validation profile required before any product exposure.",
        ),
        validation_profile=ValidationProfile.ARCHIVE_ONLY,
        cadence=CadenceClass.ARCHIVE_ON_DEMAND,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="5.8 m; 24-day revisit; 1995–2007. Historical LISS-3 archive via Bhoonidhi/NRSC.",
    ),
)

# ---------------------------------------------------------------------------
# 19. NAIP (USDA Aerial) — reference only / out-of-AOI for bangalore-60km
# ---------------------------------------------------------------------------
# SRC-006: NAIP is US-only and must remain reference/out-of-AOI for India deployments.
# No executable source row is created for bangalore-60km.

_register(
    _row(
        catalog_slug="naip",
        catalog_platform="NAIP (USDA Aerial)",
        source_id="naip-reference-only",
        provider_adapter="usda",
        product_family="aerial_optical",
        instrument_mode="NAIP",
        product_variant="FullState-Mosaics",
        analysis_level="L1",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_EMPTY_CAPS,
        product_exposure=ProductExposure.REFERENCE_ONLY,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.REFERENCE_ONLY,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "SRC-006: NAIP is USA-only; out-of-AOI for bangalore-60km and all India deployments.",
            "No executable ingestion pipeline for India deployments.",
        ),
        validation_profile=ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.REFERENCE,
        host_pool=HostPool.NONE,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="1 m; yearly cycle; USA aerial program (USDA FSA). "
              "Catalogue reference only for the Akasha India deployment.",
    ),
)

# ---------------------------------------------------------------------------
# 20. NISAR (ISRO/NASA) — data-gated SAR
# ---------------------------------------------------------------------------

_register(
    _row(
        catalog_slug="nisar",
        catalog_platform="NISAR",
        source_id="nisar-ssar-beta-gcov",
        provider_adapter="bhoonidhi",
        product_family="sar",
        instrument_mode="S-SAR",
        product_variant="Beta-GCOV",
        analysis_level="L2-GCOV",
        lifecycle_state=LifecycleState.PROVIDER_CONFIGURED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=_SEARCH_DOWNLOAD_PREPARE,
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(
            "Live since 30 Jul 2025; calibrated ARD/GCOV products not yet validated "
            "for Akasha pipeline.",
            "SAR backscatter validation profile required before product exposure.",
            "GEO-002: L+S band SAR; no optical vegetation indices.",
            "Dual-provider path (bhoonidhi + asf/earthdata) requires adapter selection.",
        ),
        validation_profile=ValidationProfile.SAR_BACKSCATTER,
        cadence=CadenceClass.TEN_TO_TWENTY_DAYS,
        host_pool=HostPool.STAGING_BHOONIDHI,
        owned_by=OwnedBy.MANUAL_ONLY,
        notes="L+S band SAR; 3–10 m; 12-day revisit; 240 km swath. "
              "Retained for prepare-script dispatch compatibility. "
              "Primary soil-mapping/biomass recommendation post-ARD validation.",
    ),
)
# fmt: on


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_source_row(source_id: str) -> SourceStateRow:
    """Return the SourceStateRow for a source_id or raise KeyError."""
    try:
        return SOURCE_REGISTRY[source_id]
    except KeyError as exc:
        raise KeyError(f"unknown source in source_registry: {source_id!r}") from exc


def source_ids_by_catalog_slug(slug: str) -> list[str]:
    """Return all source_ids that map to a given catalogSlug, sorted."""
    return sorted(r.source_id for r in SOURCE_REGISTRY.values() if r.catalog_slug == slug)


def executable_source_ids(
    *,
    aoi_id: str | None = None,
    provider_adapter: str | None = None,
) -> list[str]:
    """Return sorted source IDs that are in an executable schedule state.

    Filters optionally by AOI and provider adapter.  Only ROUTINE and
    BACKGROUND_ONLY rows are considered executable for routine runs.
    ARCHIVE_ONLY, MANUAL_ONLY, DISABLED, DRY_RUN, and DISABLED
    are excluded.
    """
    _executable = {ScheduleState.ROUTINE, ScheduleState.BACKGROUND_ONLY}
    results = []
    for row in SOURCE_REGISTRY.values():
        if row.schedule_state not in _executable:
            continue
        if provider_adapter is not None and row.provider_adapter != provider_adapter:
            continue
        if aoi_id is not None and row.default_aoi_ids and aoi_id not in row.default_aoi_ids:
            continue
        results.append(row.source_id)
    return sorted(results)


def product_active_source_ids() -> list[str]:
    """Return sorted source IDs with product_active product exposure."""
    return sorted(
        r.source_id
        for r in SOURCE_REGISTRY.values()
        if r.product_exposure == ProductExposure.PRODUCT_ACTIVE
    )


def all_catalog_slugs() -> list[str]:
    """Return the de-duplicated sorted set of catalogSlug values in the registry."""
    return sorted({r.catalog_slug for r in SOURCE_REGISTRY.values()})


# ---------------------------------------------------------------------------
# Self-check (run as module for quick sanity validation)
# ---------------------------------------------------------------------------

def _selfcheck() -> None:
    """Run basic invariant checks; raise AssertionError on any failure."""
    # All 20 catalogue slugs must be represented
    expected_slugs = {
        "resourcesat-2a", "sentinel-2", "sentinel-1",
        "landsat-8", "landsat-9", "modis",
        "cartosat-3", "eos-04-risat", "eos-06-oceansat-3",
        "alos-2-palsar-2", "superview-neo-1", "planetscope",
        "skysat", "blacksky-gen-3", "kompsat-3a",
        "landsat-7", "landsat-5", "irs-1c",
        "naip", "nisar",
    }
    registered_slugs = {r.catalog_slug for r in SOURCE_REGISTRY.values()}
    missing = expected_slugs - registered_slugs
    assert not missing, f"missing catalogue slugs: {missing}"

    # NAIP must be disabled and reference_only aoi_scope
    naip = SOURCE_REGISTRY["naip-reference-only"]
    assert naip.schedule_state == ScheduleState.DISABLED
    assert naip.aoi_scope == AoiScope.REFERENCE_ONLY
    assert naip.product_exposure == ProductExposure.REFERENCE_ONLY

    # ResourceSat-2A has exactly 3 rows
    rs2a_rows = source_ids_by_catalog_slug("resourcesat-2a")
    assert len(rs2a_rows) == 3, f"expected 3 resourcesat-2a rows, got {rs2a_rows}"

    # Only ISRO/Bhoonidhi sources should be executable initially
    active = executable_source_ids()
    non_bhoonidhi = [
        sid for sid in active
        if SOURCE_REGISTRY[sid].provider_adapter != "bhoonidhi"
    ]
    assert not non_bhoonidhi, f"non-bhoonidhi sources are executable: {non_bhoonidhi}"

    # product_active sources must be routine-scheduled (not background)
    for sid in product_active_source_ids():
        row = SOURCE_REGISTRY[sid]
        assert row.schedule_state == ScheduleState.ROUTINE, (
            f"{sid}: product_active but not ROUTINE"
        )

    # No source should have ORDER capability while commercial_blocked
    for row in SOURCE_REGISTRY.values():
        if row.commercial_state == CommercialState.COMMERCIAL_BLOCKED:
            assert Capability.ORDER not in row.capabilities, (
                f"{row.source_id}: commercial_blocked but has ORDER capability"
            )

    # All 20 catalogue slugs covered
    assert len(expected_slugs) == 20
    assert len(SOURCE_REGISTRY) >= 20  # may have more (ALOS-2 has 2 rows)

    print(
        f"[source_registry] selfcheck passed: {len(SOURCE_REGISTRY)} rows, "
        f"{len(registered_slugs)} catalogue slugs"
    )


if __name__ == "__main__":
    _selfcheck()
