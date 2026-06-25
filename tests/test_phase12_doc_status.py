"""Phase 12 documentation-status tests.

Verifies that TASK-073 through TASK-079 in the scheduler implementation plan
are marked as ``Partial (docs+tests)`` rather than any ``Yes`` status.  This guards
against accidentally promoting a docs+tests-only task to a "code complete"
status without the real provider-adapter implementation work.

Relevant file:
  docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPL_PLAN = (
    REPO_ROOT
    / "docs"
    / "impl-plan"
    / "architecture-satellite-ingestion-scheduler-1.md"
)

# Phase 12 task IDs and their brief descriptions for clear failure messages.
PHASE12_TASKS = {
    "TASK-073": "CDSE Phase (Sentinel-2/1)",
    "TASK-074": "USGS Phase (Landsat 8/9)",
    "TASK-075": "Earthdata Phase (MODIS/NISAR ASF)",
    "TASK-076": "ISRO gated Phase (EOS-04/06/NISAR/IRS-1C/Cartosat)",
    "TASK-077": "Archive Phase (Landsat 7/5, IRS-1C)",
    "TASK-078": "Commercial Phase (Planet/JAXA/VHR)",
    "TASK-079": "NAIP Phase (reference-only)",
}


def _load_impl_plan() -> str:
    assert IMPL_PLAN.exists(), f"Implementation plan not found: {IMPL_PLAN}"
    return IMPL_PLAN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def impl_plan_text() -> str:
    return _load_impl_plan()


def test_phase12_tasks_exist_in_impl_plan(impl_plan_text: str) -> None:
    """All Phase 12 task IDs must be present in the implementation plan."""
    missing = [tid for tid in PHASE12_TASKS if tid not in impl_plan_text]
    assert not missing, (
        f"Phase 12 task IDs missing from implementation plan: {missing}\n"
        f"Expected file: {IMPL_PLAN}"
    )


@pytest.mark.parametrize("task_id,description", list(PHASE12_TASKS.items()))
def test_phase12_task_marked_partial_docs_tests_not_yes(
    impl_plan_text: str, task_id: str, description: str
) -> None:
    """Each Phase 12 task must be marked ``Partial (docs+tests)``, not ``Yes``.

    Any ``Yes`` status would overclaim code-complete status for tasks that are
    only documented and tested (Phase 12 provider adapters are not yet implemented).
    """
    # Find all table rows containing the task ID.
    # Table rows look like: | TASK-073 | ... | Partial (docs+tests) | 2026-06-25 |
    row_pattern = re.compile(
        r"\|[^|]*" + re.escape(task_id) + r"[^|]*\|[^|]*\|([^|]*)\|",
        re.IGNORECASE,
    )
    matches = row_pattern.findall(impl_plan_text)
    assert matches, (
        f"{task_id} ({description}): no table row found in implementation plan"
    )

    # Every matching completed-column cell must say "Partial (docs+tests)", not any
    # "Yes" variant that would overclaim provider implementation completion.
    for cell in matches:
        cell_stripped = cell.strip()
        assert re.fullmatch(r"partial\s*\(docs\+tests\)", cell_stripped, re.IGNORECASE), (
            f"{task_id} ({description}): completed column must be 'Partial (docs+tests)' "
            f"(not bare 'Yes', a qualified 'Yes', or empty), but got: {cell_stripped!r}"
        )


def test_phase12_section_is_present(impl_plan_text: str) -> None:
    """The 'Phase 12' section must exist and reference GOAL-012 in the plan."""
    assert "Phase 12" in impl_plan_text, (
        "Implementation plan does not contain a 'Phase 12' section"
    )
    assert "GOAL-012" in impl_plan_text, (
        "Implementation plan does not reference GOAL-012 (future provider onboarding)"
    )
