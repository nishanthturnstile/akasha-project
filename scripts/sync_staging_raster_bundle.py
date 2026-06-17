"""Pull a final ResourceSat composite bundle from staging into local dev.

This is a developer convenience wrapper around the existing ingestion flow.
It does not call Bhoonidhi and it does not copy raw Bhoonidhi downloads. It
copies only final prepared artifacts:

    data/seed/rasters/<source>/composite/<aoi>/<date>/
        analytic.tif
        mask.tif
        prepare_manifest.json

After the bundle is local, --import-local can populate the local Docker MinIO
bucket and pgSTAC catalog using worker.py ingest-manifest.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = os.environ.get("AKASHA_STAGING_SSH_HOST", "akasha-staging")
DEFAULT_SOURCE = "resourcesat-2a-liss3-boa"
DEFAULT_AOI = "bangalore-60km"
DEFAULT_REMOTE_ROOT = "/srv/akasha/data/seed/rasters"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _run(args: list[str], *, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(args))
    return subprocess.run(args, cwd=cwd, text=True, check=True)


def _ssh_capture(host: str, script: str) -> str:
    result = subprocess.run(
        ["ssh", host, "bash -lc " + _quote(script)],
        cwd=REPO_ROOT,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def _remote_composite_dir(args: argparse.Namespace) -> str:
    base = posixpath.join(args.remote_root.rstrip("/"), args.source, "composite", args.aoi)
    if args.date:
        remote_dir = posixpath.join(base, args.date)
        check = (
            "test -f "
            + _quote(posixpath.join(remote_dir, "prepare_manifest.json"))
            + " && printf '%s\\n' "
            + _quote(remote_dir)
        )
        return _ssh_capture(args.host, check)

    script = rf"""
set -euo pipefail
base={_quote(base)}
latest="$(
  find "$base" -mindepth 2 -maxdepth 2 -type f -name prepare_manifest.json -printf '%h\n' \
    | sort \
    | tail -n 1
)"
test -n "$latest"
printf '%s\n' "$latest"
"""
    return _ssh_capture(args.host, script)


def _safe_extract_tar_stream(stream, destination: Path, expected_prefix: str) -> None:
    destination = destination.resolve()
    expected = PurePosixPath(expected_prefix)
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"refusing unsafe tar member: {member.name}")
            if member_path != expected and expected not in member_path.parents:
                raise RuntimeError(
                    f"refusing unexpected tar member outside {expected_prefix}: {member.name}"
                )
            target = (destination / Path(*member_path.parts)).resolve()
            if destination not in target.parents and target != destination:
                raise RuntimeError(f"refusing path outside destination: {member.name}")
            archive.extract(member, destination)


def _pull_bundle(args: argparse.Namespace, remote_dir: str) -> Path:
    relative = posixpath.relpath(remote_dir, args.remote_root.rstrip("/"))
    local_root = (REPO_ROOT / args.local_root).resolve()
    local_dir = local_root / Path(*PurePosixPath(relative).parts)

    if local_dir.exists():
        if not args.overwrite:
            raise SystemExit(
                f"local bundle already exists: {local_dir}\n"
                "Pass --overwrite to replace it."
            )
        shutil.rmtree(local_dir)

    local_root.mkdir(parents=True, exist_ok=True)
    remote_command = (
        "set -euo pipefail; cd "
        + _quote(args.remote_root.rstrip("/"))
        + " && tar -czf - "
        + _quote(relative)
    )
    print(f"pulling {args.host}:{remote_dir}")
    proc = subprocess.Popen(
        ["ssh", args.host, "bash -lc " + _quote(remote_command)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.stdout is None:
        raise RuntimeError("ssh stdout pipe was not created")
    try:
        _safe_extract_tar_stream(proc.stdout, local_root, relative)
    finally:
        proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(stderr or f"ssh/tar failed with exit code {rc}")

    manifest = local_dir / "prepare_manifest.json"
    if not manifest.is_file():
        raise SystemExit(f"bundle pulled but manifest is missing: {manifest}")
    print(f"local bundle: {local_dir}")
    return manifest


def _container_manifest_path(manifest: Path) -> str:
    relative = manifest.resolve().relative_to(REPO_ROOT / "data")
    return "/app/data/" + relative.as_posix()


def _import_local(args: argparse.Namespace, manifest: Path) -> None:
    compose = str((REPO_ROOT / "infra" / "docker" / "docker-compose.yml").resolve())
    container_manifest = _container_manifest_path(manifest)
    _run(
        [
            "docker",
            "compose",
            "-f",
            compose,
            "run",
            "--rm",
            "ingestion-worker",
            "python",
            "worker.py",
            "seed-stac",
            "--collection-id",
            args.source,
            "--method",
            "upsert",
        ]
    )
    command = [
        "docker",
        "compose",
        "-f",
        compose,
        "run",
        "--rm",
        "ingestion-worker",
        "python",
        "worker.py",
        "ingest-manifest",
        "--manifest-glob",
        container_manifest,
        "--collection-id",
        args.source,
        "--method",
        "upsert",
    ]
    if args.force_upload:
        command.append("--force")
    _run(command)


def _verify_local(args: argparse.Namespace, manifest: Path) -> None:
    compose = str((REPO_ROOT / "infra" / "docker" / "docker-compose.yml").resolve())
    command = [
        "docker",
        "compose",
        "-f",
        compose,
        "run",
        "--rm",
        "ingestion-worker",
        "python",
        "worker.py",
        "verify-composite",
        "--source",
        args.source,
        "--aoi",
        args.aoi,
        "--manifest",
        _container_manifest_path(manifest),
    ]
    if args.local_only_verify:
        command.append("--local-only")
    _run(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="SSH host for the staging VM.")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--aoi", default=DEFAULT_AOI)
    parser.add_argument("--date", help="Composite date to pull. Defaults to latest available.")
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--local-root", default="data/seed/rasters")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--import-local",
        action="store_true",
        help="After download, upload COGs into local MinIO and register the local STAC item.",
    )
    parser.add_argument(
        "--force-upload",
        action="store_true",
        help="Replace existing local MinIO objects during --import-local.",
    )
    parser.add_argument(
        "--verify-local",
        action="store_true",
        help="Run worker.py verify-composite after the bundle is present.",
    )
    parser.add_argument(
        "--local-only-verify",
        action="store_true",
        help="During --verify-local, skip the STAC catalog item check.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    remote_dir = _remote_composite_dir(args)
    manifest = _pull_bundle(args, remote_dir)
    if args.import_local:
        _import_local(args, manifest)
    if args.verify_local:
        _verify_local(args, manifest)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
