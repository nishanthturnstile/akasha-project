#!/usr/bin/env python3
"""Akasha smoke test — Slice 0 + Slice 2 (Phase 2) product surface.

Ordered checks against a running gateway/deployment:
  Slice 0:  /health, /api/health, /api/_skeleton/*
  Phase 2:  /api/config -> /api/sources -> dates -> /api/layers/default
            -> one RGB tile -> POST /api/indices/statistics

The RGB tile + statistics steps need real COGs in MinIO and a running TiTiler.
Where those are unavailable (e.g. the Emergent preview), the BFF returns a
clean 502/503 and this script reports the step as BLOCKED (not a failure), so
the contract is exercised end-to-end without fabricating raster data.

Usage:
    python scripts/smoke-test.py [BASE_URL] [--require-raster] [--login]
    BASE_URL env var also supported. Default: http://localhost:8080
    --require-raster (or REQUIRE_RASTER=1) turns BLOCKED tile/stat checks into failures.
    --login logs in before product checks using AKASHA_SMOKE_USERNAME and
    AKASHA_SMOKE_PASSWORD, then reuses the session cookie.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError

ARGS = [arg for arg in sys.argv[1:] if arg not in {"--require-raster", "--login"}]
REQUIRE_RASTER = "--require-raster" in sys.argv[1:] or os.environ.get("REQUIRE_RASTER") == "1"
LOGIN = "--login" in sys.argv[1:] or os.environ.get("AKASHA_SMOKE_LOGIN") == "1"
BASE = (ARGS[0] if ARGS else None) or os.environ.get("BASE_URL", "http://localhost:8080")
BASE = BASE.rstrip("/")

passed = failed = blocked = 0
_COOKIE_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_COOKIE_JAR))

_HEADERS = {
    "Accept": "*/*",
    "User-Agent": "akasha-smoke-test/1.0 (+https://github.com) Mozilla/5.0",
}


def _request(path: str, method: str = "GET", body: dict | None = None, timeout: float = 20.0):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(_HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except HTTPError as exc:  # 4xx/5xx still carry a body
        return exc.code, exc.read()


def check(name: str, path: str, expect_json: bool = False, want_key: str | None = None) -> None:
    global passed, failed
    try:
        status, body = _request(path)
    except (URLError, TimeoutError) as exc:
        print(f"  [x] {name}: {path} -> ERROR ({exc})")
        failed += 1
        return
    ok = status == 200
    detail = f"HTTP {status}"
    if ok and expect_json:
        try:
            data = json.loads(body)
            if want_key is not None:
                ok = want_key in data if isinstance(data, dict) else bool(data)
                detail += f", has '{want_key}'" if ok else f", missing '{want_key}'"
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"
    print(f"  [{'v' if ok else 'x'}] {name}: {path} -> {detail}")
    if ok:
        passed += 1
    else:
        failed += 1


def check_allow_blocked(
    name: str, path: str, method: str = "GET", body: dict | None = None,
    ok_statuses=(200, 204), blocked_statuses=(502, 503),
) -> None:
    """Pass on render success; report BLOCKED (not fail) when COGs/TiTiler absent."""
    global passed, failed, blocked
    try:
        status, payload = _request(path, method=method, body=body)
    except (URLError, TimeoutError) as exc:
        print(f"  [x] {name}: {path} -> ERROR ({exc})")
        failed += 1
        return
    if status in ok_statuses:
        print(f"  [v] {name}: {path} -> HTTP {status}")
        passed += 1
    elif status in blocked_statuses:
        code = ""
        try:
            code = json.loads(payload).get("error", {}).get("code", "")
        except Exception:  # noqa: BLE001
            pass
        if REQUIRE_RASTER:
            print(
                f"  [x] {name}: {path} -> HTTP {status} {code} "
                "(raster required; needs real COGs/MinIO/TiTiler)"
            )
            failed += 1
        else:
            print(
                f"  [-] BLOCKED {name}: {path} -> HTTP {status} {code} "
                "(needs real COGs/MinIO/TiTiler)"
            )
            blocked += 1
    else:
        print(f"  [x] {name}: {path} -> HTTP {status}")
        failed += 1


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def login() -> None:
    """Authenticate once and keep the session cookie in the global opener."""
    global passed, failed
    username = os.environ.get("AKASHA_SMOKE_USERNAME", "").strip()
    password = os.environ.get("AKASHA_SMOKE_PASSWORD", "")
    remember_me = _bool_env("AKASHA_SMOKE_REMEMBER_ME")
    if not username or not password:
        print(
            "  [x] login: AKASHA_SMOKE_USERNAME and AKASHA_SMOKE_PASSWORD "
            "are required when --login is used"
        )
        failed += 1
        return
    try:
        status, body = _request(
            "/api/auth/login",
            method="POST",
            body={"username": username, "password": password, "rememberMe": remember_me},
        )
    except (URLError, TimeoutError) as exc:
        print(f"  [x] login: /api/auth/login -> ERROR ({exc})")
        failed += 1
        return
    ok = status == 200
    detail = f"HTTP {status}"
    if ok:
        try:
            data = json.loads(body)
            ok = isinstance(data, dict) and "user" in data and "currentTeam" in data
            detail += ", session cookie captured" if ok else ", unexpected response JSON"
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"
    print(f"  [{'v' if ok else 'x'}] login: /api/auth/login -> {detail}")
    if ok:
        passed += 1
    else:
        failed += 1


IN_FOOTPRINT_POLY = {
    "type": "Polygon",
    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]],
}

print("=" * 64)
print(f" Akasha smoke test — Slice 0 + Phase 2   base: {BASE}")
print("=" * 64)

print("\n> Slice 0 endpoints (must pass)")
check("web/gateway health", "/health")
check("api health (proxied)", "/api/health", expect_json=True, want_key="status")
check("skeleton services", "/api/_skeleton/services", expect_json=True, want_key="services")
check("skeleton manifest", "/api/_skeleton/manifest", expect_json=True, want_key="pinnedImages")

if LOGIN:
    print("\n> Authentication (--login)")
    login()

print("\n> Phase 2 product endpoints (must pass)")
check("config", "/api/config", expect_json=True, want_key="supportedIndices")
check("sources", "/api/sources", expect_json=True, want_key="0")  # non-empty list
check("dates", "/api/sources/sentinel-2-l2a/dates", expect_json=True, want_key="0")
check("default layer", "/api/layers/default", expect_json=True, want_key="tileUrlTemplate")

print("\n> Phase 2 raster path (pass on render; BLOCKED without real COGs/TiTiler)")
check_allow_blocked(
    "rgb tile", "/api/tiles/sentinel-2-l2a/2025-09-14/rgb/12/2937/1909.png"
)
check_allow_blocked(
    "index statistics",
    "/api/indices/statistics",
    method="POST",
    body={"geometry": IN_FOOTPRINT_POLY, "sourceId": "sentinel-2-l2a",
          "acquisitionDate": "2025-09-14", "indexType": "NDVI"},
)

print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}   BLOCKED: {blocked}")
print("-" * 64)
sys.exit(1 if failed else 0)
