#!/usr/bin/env python3
"""Akasha smoke test — Slice 0 subset.

Checks the health/skeleton endpoints that exist in Slice 0, in order. The full
ordered smoke test (Phase 6/7) — /api/config -> /api/sources -> dates ->
/api/layers/default -> one RGB tile -> /api/indices/statistics — is added as
those endpoints land in later slices; they are listed here as SKIPPED so the
contract is visible without being implemented early.

Usage:
    python scripts/smoke-test.py [BASE_URL]
    BASE_URL env var also supported. Default: http://localhost:8080
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError

BASE = (len(sys.argv) > 1 and sys.argv[1]) or os.environ.get("BASE_URL", "http://localhost:8080")
BASE = BASE.rstrip("/")

passed = failed = 0


def _get(path: str, timeout: float = 10.0):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return resp.status, body


def check(name: str, path: str, expect_json: bool = False, want_key: str | None = None) -> None:
    global passed, failed
    try:
        status, body = _get(path)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"  [✗] {name}: {path} -> ERROR ({exc})")
        failed += 1
        return
    ok = status == 200
    detail = f"HTTP {status}"
    if ok and expect_json:
        try:
            data = json.loads(body)
            if want_key is not None:
                ok = want_key in data
                detail += f", has '{want_key}'" if ok else f", missing '{want_key}'"
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"
    print(f"  [{'✓' if ok else '✗'}] {name}: {path} -> {detail}")
    if ok:
        passed += 1
    else:
        failed += 1


def skip(name: str, path: str, slice_no: int) -> None:
    print(f"  [–] SKIPPED ({name}): {path}  (implemented in Slice {slice_no})")


print("=" * 64)
print(f" Akasha smoke test — Slice 0   base: {BASE}")
print("=" * 64)

print("\n▸ Slice 0 endpoints (must pass)")
check("web/gateway health", "/health")
check("api health (proxied)", "/api/health", expect_json=True, want_key="status")
check("skeleton services", "/api/_skeleton/services", expect_json=True, want_key="services")
check("skeleton manifest", "/api/_skeleton/manifest", expect_json=True, want_key="pinnedImages")

print("\n▸ Future-slice endpoints (not yet implemented)")
skip("config", "/api/config", 3)
skip("sources", "/api/sources", 3)
skip("dates", "/api/sources/sentinel-2-l2a/dates", 3)
skip("default layer", "/api/layers/default", 3)
skip("rgb tile", "/tiles/sentinel-2-l2a/<date>/rgb/12/2933/1841.png", 2)
skip("index statistics", "/api/indices/statistics", 2)

print("\n" + "-" * 64)
print(f" PASSED: {passed}   FAILED: {failed}")
print("-" * 64)
sys.exit(1 if failed else 0)
