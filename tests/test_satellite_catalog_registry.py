"""Tests for source_registry.py — TASK-004 and TASK-005.

Verifies:
  TASK-004: All 20 satellite-catalog.md slugs have a source-state row or an
            explicit out_of_aoi/reference_only exclusion; no executable row
            is missing a catalogue slug; multi-row slugs use explicit
            productVariant splits only.
  TASK-005: Commercial sources default to commercial_blocked with no
            order/task capability; archive-only sources are not routine-
            scheduled; NAIP is excluded for bangalore-60km; contradictory
            state combinations fail closed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import source_registry as sr  # noqa: E402
from akasha_ingest.source_registry import (  # noqa: E402
    _EXECUTABLE_STATES,
    _ROUTINE_SCHEDULE_STATES,
    SOURCE_REGISTRY,
    AoiScope,
    CadenceClass,
    Capability,
    CommercialState,
    LifecycleState,
    ProductExposure,
    ScheduleState,
    SourceStateRow,
    ValidationState,
    _validate_row,
)

# ---------------------------------------------------------------------------
# 20 canonical slugs from docs/reference/satellite-catalog.md
# ---------------------------------------------------------------------------
EXPECTED_CATALOG_SLUGS: frozenset[str] = frozenset(
    {
        "resourcesat-2a",
        "sentinel-2",
        "sentinel-1",
        "landsat-8",
        "landsat-9",
        "modis",
        "cartosat-3",
        "eos-04-risat",
        "eos-06-oceansat-3",
        "alos-2-palsar-2",
        "superview-neo-1",
        "planetscope",
        "skysat",
        "blacksky-gen-3",
        "kompsat-3a",
        "landsat-7",
        "landsat-5",
        "irs-1c",
        "naip",
        "nisar",
    }
)

# Commercial sources from satellite-catalog.md §3.6
COMMERCIAL_SLUGS: frozenset[str] = frozenset(
    {"superview-neo-1", "blacksky-gen-3", "kompsat-3a", "skysat", "planetscope"}
)

# Archive-only sources (decommissioned — no new acquisitions)
ARCHIVE_ONLY_SLUGS: frozenset[str] = frozenset({"landsat-7", "landsat-5", "irs-1c"})


# ---------------------------------------------------------------------------
# Helper — collect all source rows grouped by catalog_slug
# ---------------------------------------------------------------------------

def _rows_by_slug() -> dict[str, list[SourceStateRow]]:
    result: dict[str, list[SourceStateRow]] = {}
    for row in SOURCE_REGISTRY.values():
        result.setdefault(row.catalog_slug, []).append(row)
    return result


def _all_rows() -> list[SourceStateRow]:
    return list(SOURCE_REGISTRY.values())


# ===========================================================================
# TASK-004 — Catalogue slug coverage and source-row integrity
# ===========================================================================


def test_all_20_catalog_slugs_are_represented_in_registry():
    """Every satellite-catalog.md slug must appear in the source registry."""
    registered_slugs = {r.catalog_slug for r in SOURCE_REGISTRY.values()}
    missing = EXPECTED_CATALOG_SLUGS - registered_slugs
    assert not missing, (
        "The following satellite-catalog.md slugs have no source-state row in the registry:\n"
        + "\n".join(sorted(missing))
    )


def test_registry_contains_exactly_20_catalog_slugs():
    """Registry covers exactly the 20 documented platforms — no extras, no gaps."""
    registered_slugs = {r.catalog_slug for r in SOURCE_REGISTRY.values()}
    assert len(EXPECTED_CATALOG_SLUGS) == 20
    extra = registered_slugs - EXPECTED_CATALOG_SLUGS
    assert not extra, f"Unexpected slug(s) not in satellite-catalog.md: {sorted(extra)}"


def test_no_executable_row_missing_catalog_slug():
    """Every executable source row must have a non-empty catalog_slug.

    Executable = SCHEDULED, BACKGROUND_ONLY, DRY_RUN_ONLY, MANUAL_ONLY, or
    ARCHIVE_ONLY (i.e. any state that causes the scheduler to attempt work).
    """
    offenders = [
        row.source_id
        for row in SOURCE_REGISTRY.values()
        if row.schedule_state in _EXECUTABLE_STATES and not row.catalog_slug
    ]
    assert not offenders, (
        f"Executable rows missing catalog_slug: {offenders}"
    )


def test_multi_row_slugs_use_explicit_product_variant_split():
    """A catalogue slug may map to multiple source rows only through an explicit
    instrument/productVariant split: the combined (instrument_mode, product_variant)
    key must be unique and non-empty across all sibling rows.
    """
    rows_by_slug = _rows_by_slug()
    violations: list[str] = []
    for slug, rows in rows_by_slug.items():
        if len(rows) <= 1:
            continue
        for row in rows:
            if not row.product_variant and not row.instrument_mode:
                violations.append(
                    f"{slug!r}: source {row.source_id!r} has multiple sibling rows "
                    f"but both instrument_mode and product_variant are empty"
                )
        # The (instrument_mode, product_variant) combination must be distinct
        split_keys = [(row.instrument_mode, row.product_variant) for row in rows]
        if len(split_keys) != len(set(split_keys)):
            violations.append(
                f"{slug!r}: duplicate (instrument_mode, product_variant) combinations "
                f"among sibling rows: {split_keys}"
            )
    assert not violations, "\n".join(violations)


def test_resourcesat_2a_maps_to_exactly_three_source_rows():
    """ResourceSat-2A has exactly 3 rows: liss3-boa, liss4-mx70-l2, awifs-boa."""
    rs2a_ids = sr.source_ids_by_catalog_slug("resourcesat-2a")
    assert sorted(rs2a_ids) == [
        "resourcesat-2a-awifs-boa",
        "resourcesat-2a-liss3-boa",
        "resourcesat-2a-liss4-mx70-l2",
    ], f"Unexpected resourcesat-2a source rows: {rs2a_ids}"


def test_out_of_aoi_and_reference_only_rows_cover_excluded_slugs():
    """Excluded slugs (naip) must have an explicit out_of_aoi or reference_only row."""
    excluded_aoi_scopes = frozenset({AoiScope.OUT_OF_AOI, AoiScope.REFERENCE_ONLY})

    rows_by_slug = _rows_by_slug()

    # NAIP must have at least one row with out_of_aoi or reference_only aoi_scope
    naip_rows = rows_by_slug.get("naip", [])
    assert naip_rows, "naip slug has no source rows in the registry"
    naip_excluded = [
        r for r in naip_rows
        if r.aoi_scope in excluded_aoi_scopes
    ]
    assert naip_excluded, (
        "naip slug has no row marked as out_of_aoi / reference_only"
    )


# ===========================================================================
# TASK-005 — State invariants and fail-closed validation
# ===========================================================================


# --- Commercial sources -------------------------------------------------------


def test_commercial_sources_default_to_commercial_blocked():
    """Satellites documented as 💼 Commercial must have commercial_blocked state."""
    rows_by_slug = _rows_by_slug()
    violations: list[str] = []
    for slug in COMMERCIAL_SLUGS:
        rows = rows_by_slug.get(slug, [])
        non_blocked = [
            r.source_id
            for r in rows
            if r.commercial_state != CommercialState.COMMERCIAL_BLOCKED
        ]
        if non_blocked:
            violations.append(
                f"{slug!r}: expected commercial_blocked for {non_blocked}"
            )
    assert not violations, "\n".join(violations)


def test_commercial_blocked_sources_have_no_order_capability():
    """commercial_blocked rows must not expose ORDER, POLL_ORDER, or CANCEL_ORDER."""
    order_caps = frozenset({Capability.ORDER, Capability.POLL_ORDER, Capability.CANCEL_ORDER})
    violations = [
        row.source_id
        for row in SOURCE_REGISTRY.values()
        if row.commercial_state == CommercialState.COMMERCIAL_BLOCKED
        and row.capabilities & order_caps
    ]
    assert not violations, (
        f"commercial_blocked rows expose order capability: {violations}"
    )


def test_all_commercial_slug_rows_are_commercial_blocked():
    """No row for a commercial slug slips through with commercial_ready."""
    rows_by_slug = _rows_by_slug()
    for slug in COMMERCIAL_SLUGS:
        for row in rows_by_slug.get(slug, []):
            assert row.commercial_state == CommercialState.COMMERCIAL_BLOCKED, (
                f"{slug!r} / {row.source_id!r}: commercial source has "
                f"commercial_state={row.commercial_state.value!r}; "
                f"expected commercial_blocked"
            )


# --- Archive-only sources -----------------------------------------------------


def test_archive_only_slugs_use_archive_on_demand_cadence():
    """Decommissioned satellite rows must use ARCHIVE_ON_DEMAND cadence."""
    rows_by_slug = _rows_by_slug()
    for slug in ARCHIVE_ONLY_SLUGS:
        for row in rows_by_slug.get(slug, []):
            assert row.cadence == CadenceClass.ARCHIVE_ON_DEMAND, (
                f"{slug!r} / {row.source_id!r}: expected archive_on_demand cadence, "
                f"got {row.cadence.value!r}"
            )


def test_archive_only_sources_are_not_routine_scheduled():
    """Archive-only satellite rows must not use SCHEDULED or BACKGROUND_ONLY."""
    rows_by_slug = _rows_by_slug()
    violations: list[str] = []
    for slug in ARCHIVE_ONLY_SLUGS:
        for row in rows_by_slug.get(slug, []):
            if row.schedule_state in _ROUTINE_SCHEDULE_STATES:
                violations.append(
                    f"{slug!r} / {row.source_id!r}: archive-only but "
                    f"schedule_state={row.schedule_state.value!r}"
                )
    assert not violations, "\n".join(violations)


def test_archive_on_demand_cadence_rows_are_not_routine_scheduled():
    """Any row with archive_on_demand cadence must not be routine-scheduled.

    Covers future rows that may have archive_on_demand cadence for sources not
    in ARCHIVE_ONLY_SLUGS (e.g. ALOS-2 annual mosaic).
    """
    violations = [
        f"{row.source_id!r}: archive_on_demand cadence + {row.schedule_state.value!r}"
        for row in SOURCE_REGISTRY.values()
        if row.cadence == CadenceClass.ARCHIVE_ON_DEMAND
        and row.schedule_state in _ROUTINE_SCHEDULE_STATES
    ]
    assert not violations, (
        "archive_on_demand rows must not be routine-scheduled:\n"
        + "\n".join(violations)
    )


# --- NAIP exclusion -----------------------------------------------------------


def test_naip_is_reference_only_and_out_of_aoi():
    """NAIP must be disabled and reference_only aoi_scope — not executable for Bangalore."""
    naip_row = SOURCE_REGISTRY["naip-reference-only"]
    assert naip_row.schedule_state == ScheduleState.DISABLED, (
        f"naip schedule_state is {naip_row.schedule_state.value!r}; expected disabled"
    )
    assert naip_row.aoi_scope == AoiScope.REFERENCE_ONLY, (
        f"naip aoi_scope is {naip_row.aoi_scope.value!r}; expected reference_only"
    )
    assert naip_row.product_exposure != ProductExposure.PRODUCT_ACTIVE, (
        "naip must not have product_active exposure"
    )


def test_naip_has_no_bangalore_60km_aoi():
    """No NAIP row may declare bangalore-60km as a default_aoi_id."""
    naip_rows = [r for r in SOURCE_REGISTRY.values() if r.catalog_slug == "naip"]
    for row in naip_rows:
        assert "bangalore-60km" not in row.default_aoi_ids, (
            f"{row.source_id!r}: NAIP row must not target bangalore-60km"
        )


def test_naip_is_not_executable():
    """NAIP rows must not appear in executable_source_ids for any AOI."""
    executable = sr.executable_source_ids()
    naip_ids = [sid for sid in executable if "naip" in sid.lower()]
    assert not naip_ids, f"NAIP source IDs are executable: {naip_ids}"


# --- Fail-closed validation helpers ------------------------------------------


def _minimal_row(**overrides) -> SourceStateRow:
    """Build a minimal valid SourceStateRow for contradiction tests."""
    defaults = dict(
        catalog_slug="test-slug",
        catalog_platform="Test Platform",
        source_id="test-source-id",
        provider_adapter="test",
        product_family="optical_multispectral",
        instrument_mode="MS",
        product_variant="L2",
        analysis_level="L2",
        lifecycle_state=LifecycleState.CATALOGUED,
        schedule_state=ScheduleState.DISABLED,
        capabilities=frozenset(),
        product_exposure=ProductExposure.HIDDEN,
        commercial_state=CommercialState.FREE,
        aoi_scope=AoiScope.IN_AOI,
        validation_state=ValidationState.UNVALIDATED,
        readiness_reasons=(),
        validation_profile=sr.ValidationProfile.VISUAL_ONLY,
        cadence=CadenceClass.DAILY,
        host_pool=sr.HostPool.NONE,
        owned_by=sr.OwnedBy.MANUAL_ONLY,
    )
    defaults.update(overrides)
    return SourceStateRow(**defaults)


def test_validate_row_rejects_commercial_blocked_with_order():
    """commercial_blocked + ORDER must raise ValueError."""
    row = _minimal_row(
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        capabilities=frozenset({Capability.ORDER}),
    )
    with pytest.raises(ValueError, match="ORDER capability"):
        _validate_row(row)


def test_validate_row_rejects_commercial_blocked_with_poll_order():
    """commercial_blocked + POLL_ORDER must raise ValueError."""
    row = _minimal_row(
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        capabilities=frozenset({Capability.POLL_ORDER}),
    )
    with pytest.raises(ValueError, match="POLL_ORDER"):
        _validate_row(row)


def test_validate_row_rejects_commercial_blocked_with_cancel_order():
    """commercial_blocked + CANCEL_ORDER must raise ValueError."""
    row = _minimal_row(
        commercial_state=CommercialState.COMMERCIAL_BLOCKED,
        capabilities=frozenset({Capability.CANCEL_ORDER}),
    )
    with pytest.raises(ValueError, match="CANCEL_ORDER"):
        _validate_row(row)


def test_validate_row_rejects_archive_on_demand_cadence_with_scheduled():
    """archive_on_demand cadence + ROUTINE must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.ROUTINE,
        cadence=CadenceClass.ARCHIVE_ON_DEMAND,
        catalog_slug="test-slug",
    )
    with pytest.raises(ValueError, match="archive_on_demand"):
        _validate_row(row)


def test_validate_row_rejects_archive_on_demand_cadence_with_background_only():
    """archive_on_demand cadence + BACKGROUND_ONLY must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.BACKGROUND_ONLY,
        cadence=CadenceClass.ARCHIVE_ON_DEMAND,
        catalog_slug="test-slug",
        product_exposure=ProductExposure.BACKGROUND_ONLY,
    )
    with pytest.raises(ValueError, match="archive_on_demand"):
        _validate_row(row)


def test_validate_row_rejects_archive_only_schedule_with_routine_cadence():
    """ARCHIVE_ONLY schedule_state must use archive_on_demand cadence."""
    row = _minimal_row(
        schedule_state=ScheduleState.ARCHIVE_ONLY,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        catalog_slug="test-slug",
    )
    with pytest.raises(ValueError, match="archive_only"):
        _validate_row(row)


def test_validate_row_rejects_background_only_with_product_active():
    """background_only schedule_state + product_active exposure must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.BACKGROUND_ONLY,
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
        cadence=CadenceClass.DAILY,
        catalog_slug="test-slug",
    )
    with pytest.raises(ValueError, match="background_only"):
        _validate_row(row)


def test_validate_row_rejects_disabled_with_background_only_exposure():
    """disabled schedule_state + background_only product exposure must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.DISABLED,
        product_exposure=ProductExposure.BACKGROUND_ONLY,
    )
    with pytest.raises(ValueError, match="disabled"):
        _validate_row(row)


def test_validate_row_rejects_out_of_aoi_with_product_active():
    """out_of_aoi scope + product_active exposure must raise ValueError."""
    row = _minimal_row(
        aoi_scope=AoiScope.OUT_OF_AOI,
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
    )
    with pytest.raises(ValueError, match="aoi_scope"):
        _validate_row(row)


def test_validate_row_rejects_validation_failed_with_product_active():
    """validation_failed + product_active must raise ValueError."""
    row = _minimal_row(
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
        validation_state=ValidationState.VALIDATION_FAILED,
    )
    with pytest.raises(ValueError, match="validation_state=validation_passed"):
        _validate_row(row)


def test_validate_row_rejects_unvalidated_with_product_active():
    """unvalidated + product_active must raise ValueError."""
    row = _minimal_row(
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
        validation_state=ValidationState.UNVALIDATED,
    )
    with pytest.raises(ValueError, match="validation_state=validation_passed"):
        _validate_row(row)


def test_validate_row_rejects_routine_with_unvalidated():
    """routine schedule_state + unvalidated validation_state must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.ROUTINE,
        product_exposure=ProductExposure.HIDDEN,
        validation_state=ValidationState.UNVALIDATED,
        cadence=CadenceClass.FIVE_TO_TEN_DAYS,
        catalog_slug="test-slug",
    )
    with pytest.raises(ValueError, match="routine"):
        _validate_row(row)


def test_validate_row_rejects_reference_only_aoi_with_product_active():
    """reference_only aoi_scope + product_active exposure must raise ValueError."""
    row = _minimal_row(
        aoi_scope=AoiScope.REFERENCE_ONLY,
        product_exposure=ProductExposure.PRODUCT_ACTIVE,
    )
    with pytest.raises(ValueError, match="aoi_scope"):
        _validate_row(row)


def test_validate_row_rejects_executable_row_missing_catalog_slug():
    """Executable rows (ROUTINE) without a catalog_slug must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.ROUTINE,
        validation_state=ValidationState.VALIDATION_PASSED,
        catalog_slug="",  # missing
    )
    with pytest.raises(ValueError, match="catalog_slug"):
        _validate_row(row)


def test_validate_row_rejects_manual_only_executable_row_missing_catalog_slug():
    """MANUAL_ONLY rows (executable) without a catalog_slug must raise ValueError."""
    row = _minimal_row(
        schedule_state=ScheduleState.MANUAL_ONLY,
        catalog_slug="",
    )
    with pytest.raises(ValueError, match="catalog_slug"):
        _validate_row(row)


# --- Registry-wide invariants ------------------------------------------------


def test_registry_total_row_count_is_at_least_20():
    """Registry must have at least 20 rows (at least one per catalogue platform)."""
    assert len(SOURCE_REGISTRY) >= 20, (
        f"Registry has only {len(SOURCE_REGISTRY)} rows; expected at least 20"
    )


def test_all_source_ids_are_unique():
    """row.source_id values must be unique and match their registry keys."""
    row_ids = [row.source_id for row in SOURCE_REGISTRY.values()]
    assert len(row_ids) == len(set(row_ids)), "duplicate row.source_id values detected"
    mismatches = [
        f"{key!r} maps to row.source_id={row.source_id!r}"
        for key, row in SOURCE_REGISTRY.items()
        if key != row.source_id
    ]
    assert not mismatches, "registry keys must match row.source_id:\n" + "\n".join(mismatches)


def test_product_active_sources_are_routine_scheduled():
    """product_active sources must be ROUTINE (not background, archive, etc.)."""
    violations = [
        row.source_id
        for row in SOURCE_REGISTRY.values()
        if row.product_exposure == ProductExposure.PRODUCT_ACTIVE
        and row.schedule_state != ScheduleState.ROUTINE
    ]
    assert not violations, (
        f"product_active sources must be ROUTINE: {violations}"
    )


def test_executable_source_ids_are_all_bhoonidhi_initially():
    """Only ISRO/Bhoonidhi sources should be routine-executable in the initial registry."""
    executable = sr.executable_source_ids()
    non_bhoonidhi = [
        sid for sid in executable
        if SOURCE_REGISTRY[sid].provider_adapter != "bhoonidhi"
    ]
    assert not non_bhoonidhi, (
        f"Non-Bhoonidhi sources are currently executable: {non_bhoonidhi}. "
        f"Enable non-ISRO sources only after their validation profiles pass."
    )


def test_all_catalog_slugs_helper_returns_exactly_20_slugs():
    """all_catalog_slugs() must return exactly 20 unique catalogue slugs."""
    slugs = sr.all_catalog_slugs()
    assert len(slugs) == 20, f"Expected 20 slugs, got {len(slugs)}: {slugs}"
    assert sorted(slugs) == sorted(EXPECTED_CATALOG_SLUGS)


def test_get_source_row_returns_correct_row():
    """get_source_row() must return the matching SourceStateRow by source_id."""
    row = sr.get_source_row("resourcesat-2a-liss3-boa")
    assert row.catalog_slug == "resourcesat-2a"
    assert row.schedule_state == ScheduleState.ROUTINE
    assert row.product_exposure == ProductExposure.PRODUCT_ACTIVE


def test_get_source_row_raises_key_error_for_unknown():
    """get_source_row() must raise KeyError for unknown source IDs."""
    with pytest.raises(KeyError, match="unknown source in source_registry"):
        sr.get_source_row("totally-unknown-source-id")


def test_source_ids_by_catalog_slug_returns_sorted_list():
    """source_ids_by_catalog_slug() must return a sorted list of source IDs."""
    ids = sr.source_ids_by_catalog_slug("resourcesat-2a")
    assert ids == sorted(ids), f"source_ids not sorted: {ids}"
    assert len(ids) == 3


def test_selfcheck_passes():
    """The built-in _selfcheck() must pass without assertion errors."""
    # If this raises, the registry has internal inconsistencies.
    sr._selfcheck()


# ===========================================================================
# Phase 7 — ISRO source-state invariants (TASK-041 through TASK-044)
# ===========================================================================


# --- TASK-041: resourcesat-2a-liss3-boa production invariants ----------------


def test_liss3_is_routine_scheduled():
    """TASK-041: liss3-boa must be ROUTINE scheduled."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.schedule_state == ScheduleState.ROUTINE, (
        f"liss3-boa schedule_state is {row.schedule_state.value!r}; expected routine"
    )


def test_liss3_has_full_optical_capabilities():
    """TASK-041: liss3-boa must have search/download/prepare/composite/validate capabilities."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    required = frozenset(
        {
            Capability.SEARCH, Capability.DOWNLOAD, Capability.PREPARE,
            Capability.COMPOSITE, Capability.VALIDATE,
        }
    )
    missing = required - row.capabilities
    assert not missing, (
        f"liss3-boa missing capabilities: {[c.value for c in missing]}"
    )


def test_liss3_is_product_active():
    """TASK-041: liss3-boa must be product_active."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.product_exposure == ProductExposure.PRODUCT_ACTIVE, (
        f"liss3-boa product_exposure is {row.product_exposure.value!r}; expected product_active"
    )


def test_liss3_min_coverage_is_95():
    """TASK-041: liss3-boa must require 95% coverage threshold."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.min_coverage_percent == 95.0, (
        f"liss3-boa min_coverage_percent is {row.min_coverage_percent}; expected 95.0"
    )


def test_liss3_validation_passed():
    """TASK-041: liss3-boa must have validation_passed state."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.validation_state == ValidationState.VALIDATION_PASSED, (
        f"liss3-boa validation_state is {row.validation_state.value!r}; expected validation_passed"
    )


def test_liss3_host_pool_is_staging_bhoonidhi():
    """TASK-041: liss3-boa must target staging_bhoonidhi host pool."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.host_pool == sr.HostPool.STAGING_BHOONIDHI, (
        f"liss3-boa host_pool is {row.host_pool.value!r}; expected staging_bhoonidhi"
    )


def test_liss3_owned_by_scheduler_active():
    """TASK-041: liss3-boa is owned by the scheduler after the cutover."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.owned_by == sr.OwnedBy.SCHEDULER_ACTIVE, (
        f"liss3-boa owned_by is {row.owned_by.value!r}; expected scheduler_active"
    )


def test_liss3_provider_is_bhoonidhi():
    """TASK-041: liss3-boa must use the bhoonidhi provider adapter."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss3-boa"]
    assert row.provider_adapter == "bhoonidhi"


# --- TASK-042: resourcesat-2a-liss4-mx70-l2 high-resolution invariants -------


def test_liss4_is_routine_product_active():
    """TASK-042: liss4-mx70-l2 must be ROUTINE and product_active."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss4-mx70-l2"]
    assert row.schedule_state == ScheduleState.ROUTINE, (
        f"liss4-mx70-l2 schedule_state is {row.schedule_state.value!r}; expected routine"
    )
    assert row.product_exposure == ProductExposure.PRODUCT_ACTIVE, (
        f"liss4-mx70-l2 product_exposure is {row.product_exposure.value!r}; expected product_active"
    )


def test_liss4_narrow_swath_acceptance():
    """TASK-042: liss4-mx70-l2 must accept narrow-swath with min_coverage_percent=10."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss4-mx70-l2"]
    assert row.min_coverage_percent == 10.0, (
        f"liss4-mx70-l2 min_coverage_percent is {row.min_coverage_percent}; expected 10.0"
    )


def test_liss4_field_intersection_semantics_in_notes_or_reasons():
    """TASK-042: liss4-mx70-l2 must document field-intersection/fallback semantics."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss4-mx70-l2"]
    combined = row.notes + " " + " ".join(row.readiness_reasons)
    assert "intersection" in combined.lower() or "fallback" in combined.lower(), (
        "liss4-mx70-l2 must mention field-intersection or fallback semantics "
        "in notes/readiness_reasons"
    )


def test_liss4_staging_host_affinity():
    """TASK-042: liss4-mx70-l2 must target staging_bhoonidhi host pool."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss4-mx70-l2"]
    assert row.host_pool == sr.HostPool.STAGING_BHOONIDHI, (
        f"liss4-mx70-l2 host_pool is {row.host_pool.value!r}; expected staging_bhoonidhi"
    )


def test_liss4_validation_passed():
    """TASK-042: liss4-mx70-l2 must have validation_passed to be product_active."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss4-mx70-l2"]
    assert row.validation_state == ValidationState.VALIDATION_PASSED


def test_liss4_provider_is_bhoonidhi():
    """TASK-042: liss4-mx70-l2 must use the bhoonidhi provider adapter."""
    row = SOURCE_REGISTRY["resourcesat-2a-liss4-mx70-l2"]
    assert row.provider_adapter == "bhoonidhi"


# --- TASK-043: resourcesat-2a-awifs-boa regional product-active invariants ---


def test_awifs_is_routine_schedule():
    """TASK-043: awifs-boa is now routine-scheduled (active product source)."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert row.schedule_state == ScheduleState.ROUTINE, (
        f"awifs-boa schedule_state is {row.schedule_state.value!r}; expected routine"
    )


def test_awifs_product_exposure_is_product_active():
    """TASK-043: awifs-boa now has product_active exposure."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert row.product_exposure == ProductExposure.PRODUCT_ACTIVE, (
        f"awifs-boa product_exposure is {row.product_exposure.value!r}; expected product_active"
    )


def test_awifs_validation_passed_without_readiness_blockers():
    """TASK-043: awifs-boa is now validation_passed with no readiness blockers."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert row.validation_state == ValidationState.VALIDATION_PASSED, (
        f"awifs-boa validation_state is {row.validation_state.value!r}; expected validation_passed"
    )
    assert row.readiness_reasons == (), (
        f"awifs-boa must have no readiness_reasons once validated; got {row.readiness_reasons!r}"
    )


def test_awifs_min_coverage_is_60():
    """TASK-043: awifs-boa uses a reachable 60% regional coverage threshold."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert row.min_coverage_percent == 60.0, (
        f"awifs-boa min_coverage_percent is {row.min_coverage_percent}; expected 60.0"
    )


def test_awifs_staging_host_affinity():
    """TASK-043: awifs-boa must target staging_bhoonidhi host pool."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert row.host_pool == sr.HostPool.STAGING_BHOONIDHI, (
        f"awifs-boa host_pool is {row.host_pool.value!r}; expected staging_bhoonidhi"
    )


def test_awifs_has_search_capability():
    """TASK-043: awifs-boa must remain search-enabled during background ingestion."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert Capability.SEARCH in row.capabilities, (
        "awifs-boa must retain SEARCH capability during background-only phase"
    )


def test_awifs_is_product_active():
    """TASK-043: awifs-boa is product_active now that 60% coverage passes."""
    row = SOURCE_REGISTRY["resourcesat-2a-awifs-boa"]
    assert row.product_exposure == ProductExposure.PRODUCT_ACTIVE, (
        "awifs-boa must be product_active now that the validated AWiFS composite "
        "meets the 60% regional coverage threshold"
    )


# --- TASK-044: Disabled/scaffolded ISRO rows ---------------------------------


def test_eos04_is_disabled_with_correct_profile():
    """TASK-044: EOS-04 must be disabled with SAR_BACKSCATTER profile and bhoonidhi provider."""
    row = SOURCE_REGISTRY["eos-04-sar-mrs-l2b"]
    assert row.schedule_state == ScheduleState.DISABLED
    assert row.provider_adapter == "bhoonidhi"
    assert row.validation_profile == sr.ValidationProfile.SAR_BACKSCATTER
    assert row.readiness_reasons, "eos-04 must document why it is disabled"


def test_eos06_is_disabled_with_correct_profile():
    """TASK-044: EOS-06 must be disabled with PRECOMPUTED_CONTEXT profile and bhoonidhi provider."""
    row = SOURCE_REGISTRY["eos-06-ocm-lac-ndvi-8day-360m"]
    assert row.schedule_state == ScheduleState.DISABLED
    assert row.provider_adapter == "bhoonidhi"
    assert row.validation_profile == sr.ValidationProfile.PRECOMPUTED_CONTEXT
    assert row.readiness_reasons, "eos-06 must document why it is disabled"


def test_nisar_is_disabled_with_correct_profile():
    """TASK-044: NISAR must be disabled with SAR_BACKSCATTER profile and bhoonidhi provider."""
    row = SOURCE_REGISTRY["nisar-ssar-beta-gcov"]
    assert row.schedule_state == ScheduleState.DISABLED
    assert row.provider_adapter == "bhoonidhi"
    assert row.validation_profile == sr.ValidationProfile.SAR_BACKSCATTER
    assert row.readiness_reasons, "nisar must document why it is disabled"


def test_irs1c_is_archive_only_with_correct_profile():
    """TASK-044: IRS-1C must be archive_only with ARCHIVE_ONLY profile and bhoonidhi provider."""
    row = SOURCE_REGISTRY["irs-1c-liss3-archive"]
    assert row.schedule_state == ScheduleState.ARCHIVE_ONLY
    assert row.provider_adapter == "bhoonidhi"
    assert row.validation_profile == sr.ValidationProfile.ARCHIVE_ONLY
    assert row.cadence == CadenceClass.ARCHIVE_ON_DEMAND
    assert row.readiness_reasons, "irs-1c must document archive-only rationale"


def test_cartosat3_is_scaffolded_and_gated():
    """TASK-044: Cartosat-3 must be a manual-only placeholder with VISUAL_ONLY profile."""
    row = SOURCE_REGISTRY["cartosat-3-gated"]
    assert row.schedule_state == ScheduleState.MANUAL_ONLY, (
        f"cartosat-3-gated schedule_state is {row.schedule_state.value!r}; "
        f"expected manual_only"
    )
    assert row.validation_profile == sr.ValidationProfile.VISUAL_ONLY
    assert row.readiness_reasons, "cartosat-3 must document gating reason"


def test_isro_disabled_rows_are_not_executable():
    """TASK-044: Disabled ISRO scaffolded rows must not appear in executable_source_ids()."""
    gated_ids = {
        "eos-04-sar-mrs-l2b",
        "eos-06-ocm-lac-ndvi-8day-360m",
        "nisar-ssar-beta-gcov",
        "cartosat-3-gated",
    }
    executable = set(sr.executable_source_ids())
    leaked = gated_ids & executable
    assert not leaked, (
        f"Disabled ISRO rows leaked into executable_source_ids: {leaked}"
    )


# ===========================================================================
# Phase 12 — Future provider onboarding sequence (TASK-073 through TASK-079)
# ===========================================================================
#
# These tests prove that Phase 12 source-state guardrails are enforced by the
# existing registry *before* any adapter implementation begins.  They document
# invariants that must remain true throughout Phases 0–11 and gate each Phase
# 12 provider phase.
# ===========================================================================


# ---------------------------------------------------------------------------
# TASK-073: CDSE (Sentinel-2, Sentinel-1) — disabled + hidden until adapter
# ---------------------------------------------------------------------------


def test_sentinel2_is_disabled_and_hidden():
    """TASK-073: sentinel-2-l2a must remain disabled + hidden before CDSE adapter is live."""
    row = SOURCE_REGISTRY["sentinel-2-l2a"]
    assert row.schedule_state == ScheduleState.DISABLED, (
        f"sentinel-2-l2a schedule_state is {row.schedule_state.value!r}; expected disabled"
    )
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"sentinel-2-l2a product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_sentinel2_uses_cdse_provider():
    """TASK-073: sentinel-2-l2a must use the cdse provider adapter."""
    row = SOURCE_REGISTRY["sentinel-2-l2a"]
    assert row.provider_adapter == "cdse", (
        f"sentinel-2-l2a provider_adapter is {row.provider_adapter!r}; expected cdse"
    )


def test_sentinel2_uses_optical_composite_profile():
    """TASK-073: sentinel-2-l2a must use optical_composite validation profile."""
    row = SOURCE_REGISTRY["sentinel-2-l2a"]
    assert row.validation_profile == sr.ValidationProfile.OPTICAL_COMPOSITE, (
        f"sentinel-2-l2a validation_profile is {row.validation_profile.value!r}; "
        "expected optical_composite"
    )


def test_sentinel1_is_disabled_and_hidden():
    """TASK-073: sentinel-1-grd must remain disabled + hidden before CDSE/SAR adapter is live."""
    row = SOURCE_REGISTRY["sentinel-1-grd"]
    assert row.schedule_state == ScheduleState.DISABLED, (
        f"sentinel-1-grd schedule_state is {row.schedule_state.value!r}; expected disabled"
    )
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"sentinel-1-grd product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_sentinel1_uses_cdse_provider():
    """TASK-073: sentinel-1-grd must use the cdse provider adapter."""
    row = SOURCE_REGISTRY["sentinel-1-grd"]
    assert row.provider_adapter == "cdse", (
        f"sentinel-1-grd provider_adapter is {row.provider_adapter!r}; expected cdse"
    )


def test_sentinel1_uses_sar_backscatter_profile():
    """TASK-073: sentinel-1-grd must use sar_backscatter validation profile (GEO-002)."""
    row = SOURCE_REGISTRY["sentinel-1-grd"]
    assert row.validation_profile == sr.ValidationProfile.SAR_BACKSCATTER, (
        f"sentinel-1-grd validation_profile is {row.validation_profile.value!r}; "
        "expected sar_backscatter"
    )


def test_cdse_rows_are_not_executable():
    """TASK-073: CDSE rows must not appear in executable_source_ids() before adapter is built."""
    cdse_ids = {"sentinel-2-l2a", "sentinel-1-grd"}
    executable = set(sr.executable_source_ids())
    leaked = cdse_ids & executable
    assert not leaked, f"CDSE rows leaked into executable_source_ids: {sorted(leaked)}"


# ---------------------------------------------------------------------------
# TASK-074: USGS active Landsat (Landsat 8, Landsat 9) — disabled + hidden
# ---------------------------------------------------------------------------


def test_landsat8_is_disabled_and_hidden():
    """TASK-074: landsat-8-c2-l2 must be disabled + hidden until USGS adapter is live."""
    row = SOURCE_REGISTRY["landsat-8-c2-l2"]
    assert row.schedule_state == ScheduleState.DISABLED, (
        f"landsat-8-c2-l2 schedule_state is {row.schedule_state.value!r}; expected disabled"
    )
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"landsat-8-c2-l2 product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_landsat8_uses_usgs_provider():
    """TASK-074: landsat-8-c2-l2 must use the usgs provider adapter."""
    row = SOURCE_REGISTRY["landsat-8-c2-l2"]
    assert row.provider_adapter == "usgs", (
        f"landsat-8-c2-l2 provider_adapter is {row.provider_adapter!r}; expected usgs"
    )


def test_landsat8_uses_optical_composite_profile():
    """TASK-074: landsat-8-c2-l2 must use optical_composite validation profile."""
    row = SOURCE_REGISTRY["landsat-8-c2-l2"]
    assert row.validation_profile == sr.ValidationProfile.OPTICAL_COMPOSITE, (
        f"landsat-8-c2-l2 validation_profile is {row.validation_profile.value!r}; "
        "expected optical_composite"
    )


def test_landsat9_is_disabled_and_hidden():
    """TASK-074: landsat-9-c2-l2 must be disabled + hidden until USGS adapter is live."""
    row = SOURCE_REGISTRY["landsat-9-c2-l2"]
    assert row.schedule_state == ScheduleState.DISABLED, (
        f"landsat-9-c2-l2 schedule_state is {row.schedule_state.value!r}; expected disabled"
    )
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"landsat-9-c2-l2 product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_landsat9_uses_usgs_provider():
    """TASK-074: landsat-9-c2-l2 must use the usgs provider adapter."""
    row = SOURCE_REGISTRY["landsat-9-c2-l2"]
    assert row.provider_adapter == "usgs", (
        f"landsat-9-c2-l2 provider_adapter is {row.provider_adapter!r}; expected usgs"
    )


def test_landsat9_uses_optical_composite_profile():
    """TASK-074: landsat-9-c2-l2 must use optical_composite validation profile."""
    row = SOURCE_REGISTRY["landsat-9-c2-l2"]
    assert row.validation_profile == sr.ValidationProfile.OPTICAL_COMPOSITE, (
        f"landsat-9-c2-l2 validation_profile is {row.validation_profile.value!r}; "
        "expected optical_composite"
    )


def test_active_landsat_rows_are_not_executable():
    """TASK-074: Active Landsat rows must not be executable until USGS adapter is implemented."""
    active_landsat_ids = {"landsat-8-c2-l2", "landsat-9-c2-l2"}
    executable = set(sr.executable_source_ids())
    leaked = active_landsat_ids & executable
    assert not leaked, (
        f"Active Landsat rows leaked into executable_source_ids: {sorted(leaked)}"
    )


# ---------------------------------------------------------------------------
# TASK-075: Earthdata / ASF (MODIS, NISAR dual-provider readiness)
# ---------------------------------------------------------------------------


def test_modis_is_disabled_and_hidden():
    """TASK-075: modis-13q1-061 must be disabled + hidden (precomputed context, GEO-003)."""
    row = SOURCE_REGISTRY["modis-13q1-061"]
    assert row.schedule_state == ScheduleState.DISABLED, (
        f"modis-13q1-061 schedule_state is {row.schedule_state.value!r}; expected disabled"
    )
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"modis-13q1-061 product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_modis_uses_earthdata_provider():
    """TASK-075: modis-13q1-061 must use the earthdata provider adapter."""
    row = SOURCE_REGISTRY["modis-13q1-061"]
    assert row.provider_adapter == "earthdata", (
        f"modis-13q1-061 provider_adapter is {row.provider_adapter!r}; expected earthdata"
    )


def test_modis_uses_precomputed_context_profile():
    """TASK-075: modis-13q1-061 must use precomputed_context validation profile (GEO-003)."""
    row = SOURCE_REGISTRY["modis-13q1-061"]
    assert row.validation_profile == sr.ValidationProfile.PRECOMPUTED_CONTEXT, (
        f"modis-13q1-061 validation_profile is {row.validation_profile.value!r}; "
        "expected precomputed_context"
    )


def test_modis_is_not_executable():
    """TASK-075: MODIS must not appear in executable_source_ids()."""
    executable = sr.executable_source_ids()
    assert "modis-13q1-061" not in executable, (
        "modis-13q1-061 must not be executable (precomputed context source)"
    )


def test_nisar_mentions_dual_provider_in_readiness_reasons():
    """TASK-075: nisar-ssar-beta-gcov readiness_reasons must document the dual-provider path.

    NISAR can be acquired via Bhoonidhi (primary) or NASA ASF DAAC (alternate).  The readiness
    reasons must mention this dual path so operators know both providers exist.
    """
    row = SOURCE_REGISTRY["nisar-ssar-beta-gcov"]
    combined = " ".join(row.readiness_reasons).lower()
    assert "asf" in combined or "dual" in combined or "earthdata" in combined, (
        "nisar-ssar-beta-gcov readiness_reasons must mention the dual-provider path "
        "(bhoonidhi + asf/earthdata); got: " + repr(row.readiness_reasons)
    )


# ---------------------------------------------------------------------------
# TASK-076: ISRO gated sources — product_exposure=hidden + vendor for Cartosat
# ---------------------------------------------------------------------------


def test_eos04_product_exposure_is_hidden():
    """TASK-076: eos-04-sar-mrs-l2b must have hidden product exposure (SAR, not activated)."""
    row = SOURCE_REGISTRY["eos-04-sar-mrs-l2b"]
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"eos-04-sar-mrs-l2b product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_eos06_product_exposure_is_hidden():
    """TASK-076: eos-06-ocm-lac-ndvi-8day-360m must have hidden product exposure."""
    row = SOURCE_REGISTRY["eos-06-ocm-lac-ndvi-8day-360m"]
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"eos-06 product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_nisar_product_exposure_is_hidden():
    """TASK-076: nisar-ssar-beta-gcov must have hidden product exposure (data-gated)."""
    row = SOURCE_REGISTRY["nisar-ssar-beta-gcov"]
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"nisar product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_cartosat3_uses_vendor_provider():
    """TASK-076: cartosat-3-gated must use the vendor provider (no Bhoonidhi catalog path)."""
    row = SOURCE_REGISTRY["cartosat-3-gated"]
    assert row.provider_adapter == "vendor", (
        f"cartosat-3-gated provider_adapter is {row.provider_adapter!r}; expected vendor"
    )


def test_cartosat3_is_manual_only_vendor_hidden():
    """TASK-076: cartosat-3-gated must be exactly manual_only + vendor + hidden.

    The spec requires manual_only (not merely disabled) because Cartosat-3 has no
    programmatic catalog path and is managed via manual/VHR processes only.
    """
    row = SOURCE_REGISTRY["cartosat-3-gated"]
    assert row.schedule_state == ScheduleState.MANUAL_ONLY, (
        f"cartosat-3-gated schedule_state is {row.schedule_state.value!r}; "
        "expected manual_only"
    )
    assert row.provider_adapter == "vendor", (
        f"cartosat-3-gated provider_adapter is {row.provider_adapter!r}; expected vendor"
    )
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"cartosat-3-gated product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


def test_cartosat3_product_exposure_is_hidden():
    """TASK-076: cartosat-3-gated product_exposure must be hidden (manual VHR placeholder)."""
    row = SOURCE_REGISTRY["cartosat-3-gated"]
    assert row.product_exposure == ProductExposure.HIDDEN, (
        f"cartosat-3-gated product_exposure is {row.product_exposure.value!r}; expected hidden"
    )


# ---------------------------------------------------------------------------
# TASK-077: Archive/backfill sources — not in executable_source_ids()
# ---------------------------------------------------------------------------


def test_archive_landsat_rows_are_not_executable():
    """TASK-077: Landsat 7 and 5 archive rows must not appear in executable_source_ids()."""
    archive_ids = {"landsat-7-c2-l2", "landsat-5-c2-l2"}
    executable = set(sr.executable_source_ids())
    leaked = archive_ids & executable
    assert not leaked, (
        f"Archive Landsat rows leaked into executable_source_ids: {sorted(leaked)}"
    )


def test_archive_landsat_rows_have_archive_only_schedule_state():
    """TASK-077: Landsat 7/5 must be exactly archive_only + archive_on_demand (not disabled)."""
    for sid in ("landsat-7-c2-l2", "landsat-5-c2-l2"):
        row = SOURCE_REGISTRY[sid]
        assert row.schedule_state == ScheduleState.ARCHIVE_ONLY, (
            f"{sid!r} schedule_state is {row.schedule_state.value!r}; expected archive_only"
        )
        assert row.cadence == CadenceClass.ARCHIVE_ON_DEMAND, (
            f"{sid!r} cadence is {row.cadence.value!r}; expected archive_on_demand"
        )


def test_irs1c_archive_is_not_executable():
    """TASK-077: irs-1c-liss3-archive must not appear in executable_source_ids()."""
    executable = sr.executable_source_ids()
    assert "irs-1c-liss3-archive" not in executable, (
        "irs-1c-liss3-archive must not be executable (archive_only row)"
    )


def test_archive_backfill_rows_use_archive_on_demand_cadence():
    """TASK-077: Landsat 7/5 and IRS-1C archive source rows must use archive_on_demand cadence."""
    archive_source_ids = ["landsat-7-c2-l2", "landsat-5-c2-l2", "irs-1c-liss3-archive"]
    for sid in archive_source_ids:
        row = SOURCE_REGISTRY[sid]
        assert row.cadence == CadenceClass.ARCHIVE_ON_DEMAND, (
            f"{sid!r}: expected archive_on_demand cadence, got {row.cadence.value!r}"
        )


# ---------------------------------------------------------------------------
# TASK-078: Commercial sources — commercial_blocked + no order capability
# ---------------------------------------------------------------------------


def test_alos2_mosaic_is_not_routine_or_background_scheduled():
    """TASK-078: alos2-mosaic-25m must not be routine or background_only (archive/on-demand)."""
    row = SOURCE_REGISTRY["alos2-mosaic-25m"]
    assert row.schedule_state not in _ROUTINE_SCHEDULE_STATES, (
        f"alos2-mosaic-25m schedule_state is {row.schedule_state.value!r}; "
        "must not be routine or background_only"
    )


def test_alos2_mosaic_uses_archive_on_demand_cadence():
    """TASK-078: alos2-mosaic-25m cadence must be archive_on_demand (annual free mosaic only)."""
    row = SOURCE_REGISTRY["alos2-mosaic-25m"]
    assert row.cadence == CadenceClass.ARCHIVE_ON_DEMAND, (
        f"alos2-mosaic-25m cadence is {row.cadence.value!r}; expected archive_on_demand"
    )


def test_alos2_mosaic_is_not_executable():
    """TASK-078: alos2-mosaic-25m must not appear in executable_source_ids()."""
    executable = sr.executable_source_ids()
    assert "alos2-mosaic-25m" not in executable, (
        "alos2-mosaic-25m must not be executable (archive_on_demand + disabled)"
    )


def test_alos2_scene_is_commercial_blocked():
    """TASK-078: alos2-palsar2 (scenes) must be commercial_blocked (JAXA commercial scenes)."""
    row = SOURCE_REGISTRY["alos2-palsar2"]
    assert row.commercial_state == CommercialState.COMMERCIAL_BLOCKED, (
        f"alos2-palsar2 commercial_state is {row.commercial_state.value!r}; "
        "expected commercial_blocked"
    )


# ---------------------------------------------------------------------------
# TASK-079: NAIP — consolidated Phase 12 reference-only invariant
# ---------------------------------------------------------------------------


def test_naip_remains_reference_only_for_india_phase12():
    """TASK-079: NAIP must remain reference-only, disabled, and not executable for India AOI.

    This test consolidates the Phase 12 NAIP guardrail: NAIP is US-only coverage and must
    never be promoted to product_active or background_only for any India deployment.
    """
    naip_row = SOURCE_REGISTRY["naip-reference-only"]
    assert naip_row.schedule_state == ScheduleState.DISABLED, (
        f"naip schedule_state is {naip_row.schedule_state.value!r}; expected disabled"
    )
    assert naip_row.aoi_scope == AoiScope.REFERENCE_ONLY, (
        f"naip aoi_scope is {naip_row.aoi_scope.value!r}; expected reference_only"
    )
    assert naip_row.product_exposure not in (
        ProductExposure.PRODUCT_ACTIVE, ProductExposure.BACKGROUND_ONLY
    ), (
        f"naip product_exposure is {naip_row.product_exposure.value!r}; "
        "must not be product_active or background_only for India AOI"
    )
    executable = sr.executable_source_ids()
    assert "naip-reference-only" not in executable, (
        "naip-reference-only must not be executable for India AOI (SRC-006)"
    )
