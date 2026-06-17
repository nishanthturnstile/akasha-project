from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

ACTIVE_FILES = (
    "apps/api/app/config.py",
    "apps/api/app/repositories/auth_repo.py",
    "apps/api/app/routers/auth_router.py",
    "apps/api/app/schemas/auth.py",
    "apps/api/app/schemas/__init__.py",
    "apps/api/app/skeleton.py",
    "infra/docker/docker-compose.yml",
    "infra/selfhosted/coolify-compose.yml",
    "scripts/dev-local.sh",
)

REMOVED_BOOTSTRAP_MARKERS = (
    "AKASHA_LOCAL_ADMIN",
    "BootstrapPayload",
    "bootstrap_local_admin",
    "/auth/bootstrap",
    "require_no_password_users",
    "BOOTSTRAP_ADVISORY_LOCK_KEY",
)

REMOVED_BOOTSTRAP_ENV_MARKERS = (
    "AUTH_ALLOW_BOOTSTRAP",
    "AUTH_BOOTSTRAP_TOKEN",
    "AUTH_BOOTSTRAP_RATE_LIMIT_PER_HOUR",
)


def test_bootstrap_auth_plumbing_is_removed_from_active_code():
    offenders: list[str] = []
    for relative_path in ACTIVE_FILES:
        text = (REPO_ROOT / relative_path).read_text()
        for marker in REMOVED_BOOTSTRAP_MARKERS:
            if marker in text:
                offenders.append(f"{relative_path}: {marker}")
        for marker in REMOVED_BOOTSTRAP_ENV_MARKERS:
            if marker in text:
                offenders.append(f"{relative_path}: {marker}")

    assert offenders == []
