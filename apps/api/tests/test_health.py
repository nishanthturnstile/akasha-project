"""Slice 0 unit tests for the Akasha BFF skeleton.

Covers: health contract, error/shape of skeleton endpoints, and the
service-registry / env-matrix invariants required by the deployment docs.
"""
from fastapi.testclient import TestClient

from app.main import app
from app import skeleton

client = TestClient(app)


def test_root_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert body["slice"] == 0


def test_api_health_returns_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_services_registry_shape():
    r = client.get("/api/_skeleton/services")
    assert r.status_code == 200
    body = r.json()
    ids = {s["id"] for s in body["services"]}
    assert {
        "web",
        "api",
        "titiler",
        "stac-api",
        "postgis",
        "minio",
        "ingestion-worker",
    } <= ids
    # Only `web` is public.
    public = [s["id"] for s in body["services"] if s["public"]]
    assert public == ["web"]
    # The answering api is the only live service.
    live = [s["id"] for s in body["services"] if s["status"] == "live"]
    assert live == ["api"]


def test_manifest_lists_pinned_images_and_scope():
    r = client.get("/api/_skeleton/manifest")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == 0
    assert "ghcr.io/developmentseed/titiler:1.0.0" in body["pinnedImages"].values()
    assert body["inScope"] and body["outOfScope"]


def test_env_matrix_has_no_secrets():
    r = client.get("/api/_skeleton/env-matrix")
    assert r.status_code == 200
    services = r.json()["services"]
    # Every service in the topology (except image-only ones without env) is present.
    assert "api" in services and "titiler" in services and "stac-api" in services
    # Placeholders only — no resolved credentials.
    flat = str(services)
    assert "<" in flat  # placeholders use angle-bracket tokens


def test_registry_consistency_with_skeleton_module():
    assert len(skeleton.SERVICES) == 7
    assert skeleton.PINNED_IMAGES["titiler"].endswith(":1.0.0")
