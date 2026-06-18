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


def test_liss4_systemd_artifacts_are_isolated_from_liss3_units():
    timer = (SYSTEMD_DIR / "akasha-bhoonidhi-liss4-sync.timer").read_text()
    service = (SYSTEMD_DIR / "akasha-bhoonidhi-liss4-sync.service").read_text()
    script = (SYSTEMD_DIR / "akasha-bhoonidhi-liss4-sync.sh").read_text()
    env = (SYSTEMD_DIR / "akasha-bhoonidhi-liss4-sync.env.example").read_text()

    assert "OnCalendar=*-*-1/5 03:30:00" in timer
    assert "RandomizedDelaySec=30m" in timer
    assert "Persistent=true" in timer
    assert "Unit=akasha-bhoonidhi-liss4-sync.service" in timer

    assert "EnvironmentFile=-/etc/akasha/bhoonidhi-liss4-sync.env" in service
    assert "WorkingDirectory=/srv/akasha" in service
    assert "/srv/akasha/ingestion/bhoonidhi-liss4-sync.systemd.lock" in service
    assert "/opt/akasha/bin/akasha-bhoonidhi-liss4-sync.sh" in service
    assert "TimeoutStartSec=6h" in service

    assert "resourcesat-2a-liss4-mx70-l2" in script
    assert 'AKASHA_SYNC_SOURCE:-resourcesat-2a-liss4-mx70-l2' in script
    assert "bhoonidhi-liss4-sync.${aoi_id}.worker.lock" in script
    assert "--source \"${source_id}\"" in script
    assert "python worker.py \"${sync_args[@]}\"" in script

    assert "AKASHA_SYNC_SOURCE=resourcesat-2a-liss4-mx70-l2" in env
    assert "AKASHA_SYNC_AOI=bangalore-60km" in env
    assert "AKASHA_SYNC_WINDOW_DAYS=30" in env
    assert "AKASHA_SYNC_MAX_DOWNLOADS=3" in env


def test_liss4_installer_dry_run_outputs_liss4_unit_paths_only():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    if "system32" in bash.lower():
        pytest.skip("WSL bash cannot access this Windows workspace path directly")

    installer = SYSTEMD_DIR / "install-akasha-bhoonidhi-liss4-sync.sh"
    result = subprocess.run(
        [bash, str(installer), "--dry-run", "--enable", "--start"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "/opt/akasha/bin/akasha-bhoonidhi-liss4-sync.sh" in result.stdout
    assert "/etc/systemd/system/akasha-bhoonidhi-liss4-sync.service" in result.stdout
    assert "/etc/systemd/system/akasha-bhoonidhi-liss4-sync.timer" in result.stdout
    assert "/etc/akasha/bhoonidhi-liss4-sync.env" in result.stdout
    assert "/etc/systemd/system/akasha-bhoonidhi-sync.service" not in result.stdout
    assert "/etc/systemd/system/akasha-bhoonidhi-sync.timer" not in result.stdout
    assert "/etc/akasha/bhoonidhi-sync.env" not in result.stdout
    assert "systemctl daemon-reload" in result.stdout
    assert "systemctl enable akasha-bhoonidhi-liss4-sync.timer" in result.stdout
    assert "systemctl start akasha-bhoonidhi-liss4-sync.timer" in result.stdout
