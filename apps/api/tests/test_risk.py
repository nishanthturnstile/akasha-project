"""Field-watch risk summary tests."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from app.config import settings
from app.main import app
from app.routers import risk_router as risk
from fastapi.testclient import TestClient

client = TestClient(app)


def _plot(**overrides: Any) -> dict[str, Any]:
    start = (datetime.now(UTC).date() - timedelta(days=30)).isoformat()
    plot = {
        "id": "plot-1",
        "name": "North Field",
        "geometry": {"type": "Polygon", "coordinates": []},
        "cropType": "Paddy",
        "seasonLabel": "Kharif",
        "sowingDate": start,
        "plantingDate": None,
    }
    plot.update(overrides)
    return plot


def _stats(mean: float, acquisition_date: str, valid: float = 90, cloud: float = 5):
    return SimpleNamespace(
        acquisition_date=acquisition_date,
        statistics=SimpleNamespace(
            mean=mean,
            validPixelPercent=valid,
            cloudMaskedPercent=cloud,
        ),
        metadata={"metricsProvisional": False},
    )


def _install_common(monkeypatch, plot: dict[str, Any], means: dict[str, float | None]) -> None:
    monkeypatch.setattr(settings, "usable_pixel_threshold_percent", 70)
    monkeypatch.setattr(risk.plots_repo, "get_plot", lambda *_: plot)
    monkeypatch.setattr(risk.catalog, "supported_indices", lambda _source: ["NDVI", "NDRE", "NDMI"])
    monkeypatch.setattr(
        risk.catalog,
        "list_dates",
        lambda _source: [{"acquisitionDate": item} for item in sorted(means, reverse=True)],
    )
    monkeypatch.setattr(risk.phase10_repo, "list_scout_tasks", lambda *_: [])

    def fake_stats(*, acquisition_date, **_kwargs):
        value = means[acquisition_date]
        if value is None:
            return _stats(0.2, acquisition_date, valid=10, cloud=90)
        return _stats(value, acquisition_date)

    monkeypatch.setattr(risk, "_field_statistics", fake_stats)


def test_risk_summary_low_and_crop_stage(monkeypatch):
    today = datetime.now(UTC).date()
    _install_common(
        monkeypatch,
        _plot(),
        {
            today.isoformat(): 0.8,
            (today - timedelta(days=10)).isoformat(): 0.7,
        },
    )

    r = client.get("/api/fields/plot-1/risk/summary?indexType=NDVI")

    assert r.status_code == 200
    body = r.json()
    assert body["fieldWatchLevel"] == "low"
    assert body["cropStage"]["stageLabel"] == "vegetative"
    assert "not a disease or pest diagnostic model" in body["vegetationStressContext"]
    assert "disease or pest presence" in " ".join(body["limitations"])


def test_risk_summary_high_scouting_priority_not_diagnosis(monkeypatch):
    today = datetime.now(UTC).date()
    _install_common(
        monkeypatch,
        _plot(),
        {
            today.isoformat(): -0.8,
            (today - timedelta(days=3)).isoformat(): 0.8,
        },
    )
    monkeypatch.setattr(risk.phase10_repo, "list_scout_tasks", lambda *_: [{}, {}, {}])

    r = client.get("/api/fields/plot-1/risk/summary?indexType=NDVI")

    assert r.status_code == 200
    body = r.json()
    assert body["fieldWatchLevel"] == "high"
    assert "diagnostic" in body["vegetationStressContext"]
    assert "detected" not in r.text.lower()
    assert "spray" not in r.text.lower()


def test_risk_summary_weather_stress_is_native_unavailable(monkeypatch):
    today = datetime.now(UTC).date()
    _install_common(monkeypatch, _plot(), {today.isoformat(): 0.5})

    r = client.get("/api/fields/plot-1/risk/summary")

    assert r.status_code == 200
    weather = next(item for item in r.json()["components"] if item["id"] == "weatherStress")
    assert weather["available"] is False
    assert weather["source"] == "unavailable"
    assert weather["flags"]["heat"] is None
    assert "native weather source" in " ".join(weather["limitations"])


def test_risk_summary_unknown_without_usable_imagery(monkeypatch):
    today = datetime.now(UTC).date()
    _install_common(monkeypatch, _plot(sowingDate=None), {today.isoformat(): None})

    r = client.get("/api/fields/plot-1/risk/summary")

    assert r.status_code == 200
    body = r.json()
    assert body["fieldWatchLevel"] == "unknown"
    assert body["cropStage"]["stageLabel"] == "unknown"
    assert "excludedWeights" in body["metadata"]


def test_crop_stage_future_date_is_not_active(monkeypatch):
    future = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    _install_common(monkeypatch, _plot(sowingDate=future), {date.today().isoformat(): 0.4})

    r = client.get("/api/fields/plot-1/risk/summary")

    assert r.status_code == 200
    stage = r.json()["cropStage"]
    assert stage["stageLabel"] == "not started"
    assert stage["daysAfterStart"] is None
    assert "future" in " ".join(stage["limitations"])


def test_risk_summary_field_not_found_and_invalid_index(monkeypatch):
    monkeypatch.setattr(risk.plots_repo, "get_plot", lambda *_: None)
    missing = client.get("/api/fields/missing/risk/summary")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "FIELD_NOT_FOUND"

    _install_common(monkeypatch, _plot(), {date.today().isoformat(): 0.4})
    invalid = client.get("/api/fields/plot-1/risk/summary?indexType=BAD")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_INDEX_TYPE"
    assert "Traceback" not in invalid.text
