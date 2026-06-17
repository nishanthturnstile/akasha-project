from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_ci_runs_alembic_head_and_schema_drift_checks():
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()

    assert "api-migrations:" in workflow
    assert "postgis/postgis:16-3.5" in workflow
    assert "python -m app.cli db heads" in workflow
    assert "python -m app.cli db upgrade" in workflow
    assert "alembic check" in workflow
