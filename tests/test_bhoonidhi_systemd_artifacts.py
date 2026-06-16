import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "infra" / "selfhosted" / "systemd"


def test_sync_wrapper_uses_coolify_compose_autodetect_and_local_pull_policy():
    script = (SYSTEMD_DIR / "akasha-bhoonidhi-sync.sh").read_text()
    env = (SYSTEMD_DIR / "akasha-bhoonidhi-sync.env.example").read_text()

    assert 'AKASHA_COMPOSE_FILE:-' in script
    assert "/srv/akasha/coolify-compose.yml" in script
    assert "find /data/coolify/services" in script
    assert "AKASHA_SYNC_PULL_POLICY:-never" in script
    assert 'run --rm --pull "${pull_policy}" ingestion-worker' in script
    assert "AKASHA_SYNC_DRY_RUN" in script
    assert "AKASHA_SYNC_AOIS" in script
    assert "run_sync_for_aoi" in script
    assert "bhoonidhi-sync.${aoi_id}.worker.lock" in script
    assert "AKASHA_SYNC_PULL_POLICY=never" in env
    assert "AKASHA_SYNC_AOIS=bangalore-60km,mysore-60km" in env
    assert "AKASHA_COMPOSE_FILE=/srv/akasha/coolify-compose.yml" not in env


def test_installer_dry_run_outputs_expected_systemd_actions():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    if "system32" in bash.lower():
        pytest.skip("WSL bash cannot access this Windows workspace path directly")

    installer = SYSTEMD_DIR / "install-akasha-bhoonidhi-sync.sh"
    result = subprocess.run(
        [bash, str(installer), "--dry-run", "--enable", "--start"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "/opt/akasha/bin/akasha-bhoonidhi-sync.sh" in result.stdout
    assert "/etc/systemd/system/akasha-bhoonidhi-sync.service" in result.stdout
    assert "/etc/systemd/system/akasha-bhoonidhi-sync.timer" in result.stdout
    assert "/etc/akasha/bhoonidhi-sync.env" in result.stdout
    assert "systemctl daemon-reload" in result.stdout
    assert "systemctl enable akasha-bhoonidhi-sync.timer" in result.stdout
    assert "systemctl start akasha-bhoonidhi-sync.timer" in result.stdout
    assert "AKASHA_SYNC_DRY_RUN=true" in result.stdout
