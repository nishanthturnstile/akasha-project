from __future__ import annotations

import argparse
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from scripts import sync_staging_raster_bundle as sync


def _args(**overrides):
    values = {
        "host": "akasha-staging",
        "source": "resourcesat-2a-liss3-boa",
        "aoi": "bangalore-60km",
        "date": None,
        "remote_root": "/srv/akasha/data/seed/rasters",
        "local_root": "data/seed/rasters",
        "overwrite": False,
        "import_local": False,
        "force_upload": False,
        "verify_local": False,
        "min_coverage_percent": None,
        "local_only_verify": False,
        "job_id": None,
        "remote_manifest": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _tar_stream(member_name: str, content: bytes = b"payload") -> io.BytesIO:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    stream.seek(0)
    return stream


def _repo_scratch(name: str) -> Path:
    return sync.REPO_ROOT / ".pytest-cache" / name


def test_latest_remote_composite_lookup_uses_source_aoi_base(monkeypatch):
    calls = []

    def fake_ssh_capture(host: str, script: str) -> str:
        calls.append((host, script))
        return (
            "/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/"
            "composite/bangalore-60km/2026-06-01"
        )

    monkeypatch.setattr(sync, "_ssh_capture", fake_ssh_capture)

    remote_dir = sync._remote_composite_dir(_args())

    assert remote_dir.endswith("/composite/bangalore-60km/2026-06-01")
    assert calls[0][0] == "akasha-staging"
    script = calls[0][1]
    expected_base = (
        "base='/srv/akasha/data/seed/rasters/"
        "resourcesat-2a-liss3-boa/composite/bangalore-60km'"
    )
    assert expected_base in script
    assert "find \"$base\" -mindepth 2 -maxdepth 2 -type f -name prepare_manifest.json" in script
    assert "tail -n 1" in script


def test_date_specific_remote_composite_lookup_checks_manifest(monkeypatch):
    calls = []

    def fake_ssh_capture(host: str, script: str) -> str:
        calls.append((host, script))
        return (
            "/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/"
            "composite/bangalore-60km/2026-06-02"
        )

    monkeypatch.setattr(sync, "_ssh_capture", fake_ssh_capture)

    remote_dir = sync._remote_composite_dir(_args(date="2026-06-02"))

    assert remote_dir.endswith("/2026-06-02")
    assert calls[0][0] == "akasha-staging"
    assert (
        "test -f "
        "'/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-06-02/prepare_manifest.json'"
        in calls[0][1]
    )


@pytest.mark.parametrize(
    "member_name",
    ["/absolute/prepare_manifest.json", "../prepare_manifest.json"],
)
def test_safe_tar_extraction_refuses_absolute_paths_and_parent_references(member_name):
    with pytest.raises(RuntimeError, match="refusing unsafe tar member"):
        sync._safe_extract_tar_stream(
            _tar_stream(member_name),
            _repo_scratch("safe-extract-test"),
            "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-06-01",
        )


def test_import_local_runs_seed_stac_and_ingest_manifest(monkeypatch):
    commands = []
    monkeypatch.setattr(sync, "_run", lambda command, cwd=sync.REPO_ROOT: commands.append(command))
    manifest = (
        sync.REPO_ROOT
        / "data"
        / "seed"
        / "rasters"
        / "resourcesat-2a-liss3-boa"
        / "composite"
        / "bangalore-60km"
        / "2026-06-01"
        / "prepare_manifest.json"
    )

    sync._import_local(_args(force_upload=True), manifest)

    assert [command[7:12] for command in commands] == [
        ["python", "worker.py", "seed-stac", "--collection-id", "resourcesat-2a-liss3-boa"],
        [
            "python",
            "worker.py",
            "ingest-manifest",
            "--manifest-glob",
            "/app/data/seed/rasters/resourcesat-2a-liss3-boa/"
            "composite/bangalore-60km/2026-06-01/prepare_manifest.json",
        ],
    ]
    assert commands[1][-1] == "--force"


def test_verify_local_runs_verify_composite(monkeypatch):
    commands = []
    monkeypatch.setattr(sync, "_run", lambda command, cwd=sync.REPO_ROOT: commands.append(command))
    manifest = (
        sync.REPO_ROOT
        / "data"
        / "seed"
        / "rasters"
        / "resourcesat-2a-liss3-boa"
        / "composite"
        / "bangalore-60km"
        / "2026-06-01"
        / "prepare_manifest.json"
    )

    sync._verify_local(_args(local_only_verify=True), manifest)

    command = commands[0]
    assert command[7:10] == ["python", "worker.py", "verify-composite"]
    assert command[command.index("--source") + 1] == "resourcesat-2a-liss3-boa"
    assert command[command.index("--aoi") + 1] == "bangalore-60km"
    assert command[-1] == "--local-only"


def test_verify_local_preserves_liss4_default_min_coverage(monkeypatch):
    commands = []
    monkeypatch.setattr(sync, "_run", lambda command, cwd=sync.REPO_ROOT: commands.append(command))
    manifest = (
        sync.REPO_ROOT
        / "data"
        / "seed"
        / "rasters"
        / "resourcesat-2a-liss4-mx70-l2"
        / "composite"
        / "bangalore-60km"
        / "2026-06-01"
        / "prepare_manifest.json"
    )

    sync._verify_local(_args(source="resourcesat-2a-liss4-mx70-l2"), manifest)

    command = commands[0]
    assert command[command.index("--min-coverage-percent") + 1] == "10.0"


def test_job_id_reads_remote_result_and_uses_composite_fields(monkeypatch):
    calls = []

    def fake_ssh_capture(host: str, script: str) -> str:
        calls.append((host, script))
        if "result.json" in script:
            return json.dumps(
                {
                    "source_id": "resourcesat-2a-liss4-mx70-l2",
                    "aoi_id": "bangalore-120km",
                    "composite_date": "2026-06-03",
                }
            )
        return (
            "/srv/akasha/data/seed/rasters/resourcesat-2a-liss4-mx70-l2/"
            "composite/bangalore-120km/2026-06-03"
        )

    monkeypatch.setattr(sync, "_ssh_capture", fake_ssh_capture)
    args = _args(job_id="job-123")

    sync._resolve_pull_target(args)
    remote_dir = sync._remote_composite_dir(args)

    assert remote_dir.endswith(
        "/resourcesat-2a-liss4-mx70-l2/composite/bangalore-120km/2026-06-03"
    )
    assert args.source == "resourcesat-2a-liss4-mx70-l2"
    assert args.aoi == "bangalore-120km"
    assert args.date == "2026-06-03"
    assert "cat '/srv/akasha/ingestion/jobs/job-123/result.json'" in calls[0][1]


def test_job_id_rejects_missing_composite_date(monkeypatch):
    monkeypatch.setattr(
        sync,
        "_ssh_capture",
        lambda host, script: json.dumps(
            {
                "source_id": "resourcesat-2a-liss3-boa",
                "aoi_id": "bangalore-60km",
                "composite_date": "",
            }
        ),
    )

    with pytest.raises(SystemExit, match="composite_date is missing"):
        sync._resolve_pull_target(_args(job_id="job-123"))


def test_remote_manifest_resolves_parent_directory(monkeypatch):
    remote_manifest = (
        "/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/"
        "composite/bangalore-60km/2026-06-04/prepare_manifest.json"
    )
    args = _args(
        remote_manifest=remote_manifest,
    )

    sync._resolve_pull_target(args)
    remote_dir = sync._remote_composite_dir(args)

    assert remote_dir == (
        "/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/"
        "composite/bangalore-60km/2026-06-04"
    )
    assert args.source == "resourcesat-2a-liss3-boa"
    assert args.aoi == "bangalore-60km"
    assert args.date == "2026-06-04"


@pytest.mark.parametrize(
    "remote_manifest",
    [
        "/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/"
        "composite/bangalore-60km/2026-06-04/not_manifest.json",
        "/srv/akasha/other/prepare_manifest.json",
    ],
)
def test_remote_manifest_rejects_invalid_manifest_paths(remote_manifest):
    with pytest.raises(SystemExit):
        sync._resolve_pull_target(_args(remote_manifest=remote_manifest))


def test_pull_bundle_prints_machine_readable_summary(monkeypatch, capsys):
    relative = "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-06-05"
    stream = _tar_stream(f"{relative}/prepare_manifest.json", b"{}")
    scratch_root = _repo_scratch("pull-bundle-test")
    shutil.rmtree(scratch_root, ignore_errors=True)

    class FakeProc:
        def __init__(self):
            self.stdout = stream
            self.stderr = io.BytesIO()

        def wait(self) -> int:
            return 0

    try:
        monkeypatch.setattr(sync, "REPO_ROOT", scratch_root)
        monkeypatch.setattr(sync.subprocess, "Popen", lambda *args, **kwargs: FakeProc())
        args = _args(date="2026-06-05")

        manifest = sync._pull_bundle(
            args,
            "/srv/akasha/data/seed/rasters/resourcesat-2a-liss3-boa/"
            "composite/bangalore-60km/2026-06-05",
        )

        expected = (
            scratch_root / "data" / "seed" / "rasters" / relative / "prepare_manifest.json"
        )
        assert manifest == expected
        output = capsys.readouterr().out
        assert "local bundle:" in output
        assert f"local_manifest={manifest}" in output
        assert "source=resourcesat-2a-liss3-boa" in output
        assert "aoi=bangalore-60km" in output
        assert "date=2026-06-05" in output
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
