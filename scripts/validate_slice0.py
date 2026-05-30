#!/usr/bin/env python3
"""Slice 0 artifact validator for the Akasha Railway MVP.

The Emergent sandbox has no Docker engine, so this script proves the Slice 0
"core" the way we *can* here: by statically validating that every required
skeleton artifact exists, is well-formed, pins the approved image versions,
wires health checks, exposes only the gateway publicly, and leaks no secrets.

Run:  python scripts/validate_slice0.py
Exit: 0 if everything passes, 1 otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(2)

REPO = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# Approved pinned versions (must match apps/api/app/skeleton.py).
# --------------------------------------------------------------------------
PIN_TITILER = "ghcr.io/developmentseed/titiler:1.0.0"
PIN_STAC = "ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2"
PIN_POSTGIS = "postgis/postgis:16-3.5"
PIN_MINIO = "minio/minio:RELEASE.2025-10-15T17-29-55Z"
PIN_CADDY = "caddy:2.8-alpine"
PIN_PY = "python:3.11-slim"
PIN_NODE = "node:20-alpine"

EXPECTED_SERVICES = {
    "web",
    "api",
    "titiler",
    "stac-api",
    "postgis",
    "minio",
    "ingestion-worker",
}

REQUIRED_PATHS = [
    # source-of-truth docs (kept safe)
    "docs/engineering-dos-donts.md",
    "docs/mvp-execution-plan.md",
    "docs/railway-deployment-guide.md",
    "docs/architecture-tech-stack.md",
    "docs/emergent-context.md",
    # api
    "apps/api/app/main.py",
    "apps/api/app/skeleton.py",
    "apps/api/app/config.py",
    "apps/api/requirements.txt",
    "apps/api/Dockerfile",
    "apps/api/railway.json",
    "apps/api/.env.example",
    "apps/api/tests/test_health.py",
    # frontend
    "apps/frontend/package.json",
    "apps/frontend/index.html",
    "apps/frontend/src/App.tsx",
    "apps/frontend/Dockerfile",
    "apps/frontend/.env.example",
    # services
    "services/titiler/Dockerfile",
    "services/titiler/railway.json",
    "services/titiler/.env.example",
    "services/stac-api/Dockerfile",
    "services/stac-api/railway.json",
    "services/stac-api/.env.example",
    "services/ingestion/Dockerfile",
    "services/ingestion/worker.py",
    "services/ingestion/railway.json",
    "services/ingestion/.env.example",
    # infra
    "infra/gateway/Dockerfile",
    "infra/gateway/Caddyfile",
    "infra/gateway/.env.example",
    "infra/docker/docker-compose.yml",
    "infra/docker/.env.example",
    "infra/railway/README.md",
    "infra/railway/ENV_MATRIX.md",
    "infra/railway/web.railway.json",
    # root conventions
    "railway.json",
    "pyproject.toml",
    ".editorconfig",
    ".prettierrc.json",
    "Makefile",
    "README.md",
    # scripts
    "scripts/smoke-test.py",
]

# .env.example files that must contain placeholders only.
ENV_EXAMPLES = [
    "apps/api/.env.example",
    "apps/frontend/.env.example",
    "services/titiler/.env.example",
    "services/stac-api/.env.example",
    "services/ingestion/.env.example",
    "infra/gateway/.env.example",
    "infra/docker/.env.example",
]

# Secret-ish variable names whose values must be placeholders.
SECRET_KEY_RE = re.compile(r"(PASSWORD|SECRET|_KEY)\b", re.IGNORECASE)
PLACEHOLDER_TOKENS = ("<", "CHANGE_ME", "operator-provided")
# Hard-banned default credentials anywhere in env examples.
BANNED_TOKENS = ["minioadmin", "postgres:postgres", "password123"]

results: List[tuple] = []  # (ok: bool, message: str)


def check(ok: bool, msg: str) -> None:
    results.append((bool(ok), msg))


def section(title: str) -> None:
    results.append((None, title))


# --------------------------------------------------------------------------
# 1) Required files
# --------------------------------------------------------------------------
section("Required files & folders")
for rel in REQUIRED_PATHS:
    check((REPO / rel).exists(), f"exists: {rel}")


# --------------------------------------------------------------------------
# 2) docker-compose.yml structure
# --------------------------------------------------------------------------
section("docker-compose.yml")
compose_path = REPO / "infra/docker/docker-compose.yml"
compose = {}
if compose_path.exists():
    try:
        compose = yaml.safe_load(compose_path.read_text())
        check(True, "docker-compose.yml parses as valid YAML")
    except yaml.YAMLError as exc:  # pragma: no cover
        check(False, f"docker-compose.yml YAML parse error: {exc}")

svcs = (compose or {}).get("services", {})
check(
    EXPECTED_SERVICES <= set(svcs.keys()),
    f"all 7 services present ({sorted(EXPECTED_SERVICES)})",
)

# Only `web` publishes host ports.
ported = [name for name, cfg in svcs.items() if (cfg or {}).get("ports")]
check(ported == ["web"], f"only `web` publishes host ports (found: {ported or 'none'})")

# Health checks present for the HTTP services + datastores.
for name in ["web", "api", "titiler", "stac-api", "postgis", "minio"]:
    has_hc = bool((svcs.get(name) or {}).get("healthcheck"))
    check(has_hc, f"healthcheck defined: {name}")

# Persistent volumes for postgis + minio.
top_volumes = set((compose or {}).get("volumes", {}) or {})
check({"postgis_data", "minio_data"} <= top_volumes, "named volumes: postgis_data + minio_data")
for name, vol in [("postgis", "postgis_data"), ("minio", "minio_data")]:
    mounts = " ".join((svcs.get(name) or {}).get("volumes", []) or [])
    check(vol in mounts, f"{name} mounts persistent volume {vol}")

# Pinned images in compose.
check((svcs.get("postgis") or {}).get("image") == PIN_POSTGIS, f"postgis image == {PIN_POSTGIS}")
check((svcs.get("minio") or {}).get("image") == PIN_MINIO, f"minio image == {PIN_MINIO}")

# MinIO console disabled.
minio_env = (svcs.get("minio") or {}).get("environment", {}) or {}
check(str(minio_env.get("MINIO_BROWSER", "")).lower() == "off", "minio console disabled (MINIO_BROWSER=off)")


# --------------------------------------------------------------------------
# 3) Pinned base images in Dockerfiles
# --------------------------------------------------------------------------
section("Pinned base images (Dockerfiles)")


def dockerfile_has(rel: str, token: str) -> bool:
    p = REPO / rel
    return p.exists() and token in p.read_text()


check(dockerfile_has("services/titiler/Dockerfile", PIN_TITILER), f"titiler FROM {PIN_TITILER}")
check(dockerfile_has("services/stac-api/Dockerfile", PIN_STAC), f"stac-api FROM {PIN_STAC}")
check(dockerfile_has("infra/gateway/Dockerfile", PIN_CADDY), f"gateway uses {PIN_CADDY}")
check(dockerfile_has("infra/gateway/Dockerfile", PIN_NODE), f"gateway builds with {PIN_NODE}")
check(dockerfile_has("apps/api/Dockerfile", PIN_PY), f"api FROM {PIN_PY}")
check(dockerfile_has("services/ingestion/Dockerfile", PIN_PY), f"ingestion FROM {PIN_PY}")


# --------------------------------------------------------------------------
# 4) railway.json health check paths + valid JSON
# --------------------------------------------------------------------------
section("Railway configs")
RAILWAY_EXPECT = {
    "railway.json": ("/health", "infra/gateway/Dockerfile"),
    "apps/api/railway.json": ("/health", "Dockerfile"),
    "services/titiler/railway.json": ("/healthz", "Dockerfile"),
    "services/stac-api/railway.json": ("/_mgmt/health", "Dockerfile"),
}
for rel, (hc, dockerfile) in RAILWAY_EXPECT.items():
    p = REPO / rel
    if not p.exists():
        check(False, f"missing {rel}")
        continue
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        check(False, f"{rel} invalid JSON: {exc}")
        continue
    check(data.get("deploy", {}).get("healthcheckPath") == hc, f"{rel} healthcheckPath == {hc}")
    check(
        data.get("build", {}).get("dockerfilePath") == dockerfile,
        f"{rel} dockerfilePath == {dockerfile}",
    )

# ingestion worker railway.json is valid JSON (no healthcheck \u2014 it's a worker).
ing = REPO / "services/ingestion/railway.json"
if ing.exists():
    try:
        json.loads(ing.read_text())
        check(True, "services/ingestion/railway.json valid JSON")
    except json.JSONDecodeError as exc:
        check(False, f"services/ingestion/railway.json invalid JSON: {exc}")


# --------------------------------------------------------------------------
# 5) Caddy gateway routes
# --------------------------------------------------------------------------
section("Caddy gateway routes")
caddy = REPO / "infra/gateway/Caddyfile"
if caddy.exists():
    text = caddy.read_text()
    check("/health" in text, "Caddyfile defines /health")
    check("/api/*" in text, "Caddyfile proxies /api/*")
    check("/tiles/*" in text, "Caddyfile proxies /tiles/*")
    check("file_server" in text, "Caddyfile serves the SPA (file_server)")


# --------------------------------------------------------------------------
# 6) .env.example files contain placeholders only (no secrets/defaults)
# --------------------------------------------------------------------------
section(".env.example secret hygiene")
for rel in ENV_EXAMPLES:
    p = REPO / rel
    if not p.exists():
        check(False, f"missing {rel}")
        continue
    raw = p.read_text()
    # Only inspect assignment VALUES (ignore comments/docs that may legitimately
    # mention banned tokens, e.g. "Do NOT use minioadmin").
    values_blob = ""
    bad_lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        values_blob += value.lower() + "\n"
        if not value:
            continue  # empty (e.g., GATEWAY_BASIC_AUTH=) is fine
        if SECRET_KEY_RE.search(key):
            if not any(tok in value for tok in PLACEHOLDER_TOKENS):
                bad_lines.append(key)
    banned_hit = next((b for b in BANNED_TOKENS if b in values_blob), None)
    check(banned_hit is None, f"{rel}: no banned default creds" + (f" (found {banned_hit})" if banned_hit else ""))
    check(not bad_lines, f"{rel}: secret-like vars are placeholders" + (f" (offending: {bad_lines})" if bad_lines else ""))


# --------------------------------------------------------------------------
# 7) JSON sanity for other config files
# --------------------------------------------------------------------------
section("JSON sanity")
for rel in ["apps/frontend/package.json", ".prettierrc.json", "infra/railway/web.railway.json"]:
    p = REPO / rel
    if not p.exists():
        check(False, f"missing {rel}")
        continue
    try:
        json.loads(p.read_text())
        check(True, f"{rel} valid JSON")
    except json.JSONDecodeError as exc:
        check(False, f"{rel} invalid JSON: {exc}")


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
print("\n" + "=" * 64)
print(" Akasha \u2014 Slice 0 artifact validation")
print("=" * 64)
passed = failed = 0
for ok, msg in results:
    if ok is None:
        print(f"\n\u25b8 {msg}")
        continue
    icon = "\u2713" if ok else "\u2717"
    print(f"  [{icon}] {msg}")
    if ok:
        passed += 1
    else:
        failed += 1

print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}")
print("-" * 64)

if failed:
    print("\nSlice 0 validation FAILED \u2014 fix the items above.")
    sys.exit(1)
print("\nSlice 0 validation PASSED \u2014 skeleton artifacts are Railway-ready.")
sys.exit(0)
