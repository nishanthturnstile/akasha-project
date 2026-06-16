from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _enable_diagnostics(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "bhoonidhi_diagnostics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_user_id", "diagnostic-user", raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_password", "diagnostic-password", raising=False)
    monkeypatch.setattr(
        settings,
        "bhoonidhi_api_base",
        "https://bhoonidhi-api.nrsc.gov.in",
        raising=False,
    )
    monkeypatch.setattr(settings, "bhoonidhi_download_root", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_download_timeout_seconds", 10, raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_max_download_bytes", 10_000_000, raising=False)


def test_diagnostic_start_rejects_when_feature_flag_disabled(monkeypatch, tmp_path):
    _enable_diagnostics(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "bhoonidhi_diagnostics_enabled", False, raising=False)

    response = client.post(
        "/api/admin/bhoonidhi/diagnostics/resourcesat-boa",
        json={"collectionId": "ResourceSat-2A_LISS3_BOA", "itemId": "RS2A_TEST_PRODUCT"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BHOONIDHI_DIAGNOSTICS_DISABLED"


def test_diagnostic_start_rejects_when_credentials_missing(monkeypatch, tmp_path):
    _enable_diagnostics(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "bhoonidhi_user_id", "", raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_password", "", raising=False)

    response = client.post(
        "/api/admin/bhoonidhi/diagnostics/resourcesat-boa",
        json={"collectionId": "ResourceSat-2A_LISS3_BOA", "itemId": "RS2A_TEST_PRODUCT"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BHOONIDHI_NOT_CONFIGURED"


def test_diagnostic_start_returns_job_id_and_status_url(monkeypatch, tmp_path):
    from app.routers import bhoonidhi_router as diagnostics

    _enable_diagnostics(monkeypatch, tmp_path)
    diagnostics.clear_jobs_for_tests()
    monkeypatch.setattr(diagnostics, "_run_diagnostic_job", lambda job_id, request: None)

    response = client.post(
        "/api/admin/bhoonidhi/diagnostics/resourcesat-boa",
        json={"collectionId": "ResourceSat-2A_LISS3_BOA", "itemId": "RS2A_TEST_PRODUCT"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["jobId"]
    assert body["statusUrl"] == f"/api/admin/bhoonidhi/diagnostics/{body['jobId']}"


def test_diagnostic_status_unknown_job_returns_standard_not_found(monkeypatch, tmp_path):
    _enable_diagnostics(monkeypatch, tmp_path)

    response = client.get("/api/admin/bhoonidhi/diagnostics/missing-job")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BHOONIDHI_DIAGNOSTIC_JOB_NOT_FOUND"


def test_product_inspector_reports_bands_quality_candidates_and_missing_roles(tmp_path):
    from app.routers.bhoonidhi_router import inspect_downloaded_product

    archive_path = tmp_path / "resourcesat_product.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("product/DATA/BAND2.tif", b"not-a-real-tif")
        zf.writestr("product/DATA/BAND3.TIF", b"not-a-real-tif")
        zf.writestr("product/DATA/BAND4.tiff", b"not-a-real-tif")
        zf.writestr("product/DATA/BAND5.tif", b"not-a-real-tif")
        zf.writestr("product/DATA/QUALITY_CLOUD_MASK.tif", b"not-a-real-tif")
        zf.writestr(
            "product/metadata.xml",
            "<product><satellite>Resourcesat-2A</satellite></product>",
        )

    report = inspect_downloaded_product(archive_path)

    assert report["archive"]["kind"] == "zip"
    assert report["archive"]["entryCount"] == 6
    role_to_entries = {
        candidate["role"]: candidate["entries"] for candidate in report["bandCandidates"]
    }
    assert role_to_entries["GREEN"] == ["product/DATA/BAND2.tif"]
    assert role_to_entries["RED"] == ["product/DATA/BAND3.TIF"]
    assert role_to_entries["NIR"] == ["product/DATA/BAND4.tiff"]
    assert role_to_entries["SWIR1"] == ["product/DATA/BAND5.tif"]
    assert report["missing"]["roles"] == []
    assert report["qualityCandidates"][0]["entry"] == "product/DATA/QUALITY_CLOUD_MASK.tif"
    assert any("quality" in item.lower() for item in report["recommendations"])


def test_job_runner_sanitizes_paths_and_tokens(monkeypatch, tmp_path):
    from app.routers import bhoonidhi_router as diagnostics

    _enable_diagnostics(monkeypatch, tmp_path)
    diagnostics.clear_jobs_for_tests()

    archive_path = tmp_path / "secret-root" / "resourcesat_product.zip"
    archive_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("product/DATA/BAND2.tif", b"not-a-real-tif")
        zf.writestr("product/DATA/BAND3.tif", b"not-a-real-tif")
        zf.writestr("product/DATA/BAND4.tif", b"not-a-real-tif")
        zf.writestr("product/DATA/BAND5.tif", b"not-a-real-tif")

    def fake_download(request: Any) -> Path:
        return archive_path

    monkeypatch.setattr(diagnostics, "_download_bhoonidhi_product", fake_download)
    job = diagnostics.create_job(
        diagnostics.BhoonidhiDiagnosticRequest(
            collectionId="ResourceSat-2A_LISS3_BOA",
            itemId="RS2A_TEST_PRODUCT",
        )
    )

    diagnostics._run_diagnostic_job(job.job_id, job.request)
    public_job = diagnostics.get_public_job(job.job_id)

    assert public_job["status"] == "succeeded"
    text = str(public_job)
    assert "diagnostic-password" not in text
    assert str(tmp_path) not in text
    assert "access_token" not in text
    assert public_job["result"]["download"]["fileName"] == "resourcesat_product.zip"
