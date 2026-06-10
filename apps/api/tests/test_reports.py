"""Phase 9 reports and field leaderboard route tests."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app import reports
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _plot(plot_id: str, name: str, **overrides: Any) -> dict[str, Any]:
    plot = {
        "id": plot_id,
        "name": name,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 12.0], [77.2, 12.0], [77.2, 12.2], [77.0, 12.0]]],
        },
        "areaHa": 5.0,
        "groupName": "North",
        "cropType": "Paddy",
        "variety": "Sona",
        "seasonLabel": "Kharif",
        "sowingDate": "2026-06-01",
        "plantingDate": None,
    }
    plot.update(overrides)
    return plot


def _stats(mean: float | None, valid: float = 90, cloud: float = 5):
    return SimpleNamespace(
        acquisition_date="2026-06-01",
        statistics=SimpleNamespace(
            mean=mean,
            validPixelPercent=valid,
            cloudMaskedPercent=cloud,
        ),
        metadata={"metricsProvisional": False},
    )


def _install_leaderboard_fakes(
    monkeypatch,
    plots: list[dict[str, Any]],
    values: dict[str, list[float | None]],
):
    monkeypatch.setattr(settings, "usable_pixel_threshold_percent", 70)
    monkeypatch.setattr(reports.plots_repo, "list_plots", lambda *_: plots)
    monkeypatch.setattr(
        reports.catalog,
        "list_dates",
        lambda _source: [
            {"acquisitionDate": "2026-06-01"},
            {"acquisitionDate": "2026-05-20"},
            {"acquisitionDate": "2026-05-01"},
        ],
    )

    def fake_stats(*, plot_id, acquisition_date, **_kwargs):
        sequence = values.get(plot_id, [])
        idx = {"2026-06-01": 0, "2026-05-20": 1, "2026-05-01": 2}[acquisition_date]
        value = sequence[idx] if idx < len(sequence) else None
        if value == -999:
            return _stats(0.9, valid=5, cloud=95)
        result = _stats(value)
        result.acquisition_date = acquisition_date
        return result

    monkeypatch.setattr(reports, "_field_statistics", fake_stats)


def _assert_no_leaks(text: str) -> None:
    for leaked in ["SELECT ", "Traceback", "internal-secret"]:
        assert leaked not in text


def test_field_leaderboard_ranks_before_pagination_and_includes_location(monkeypatch):
    plots = [
        _plot("plot-a", "Alpha"),
        _plot("plot-b", "Beta"),
        _plot("plot-c", "Gamma"),
    ]
    _install_leaderboard_fakes(
        monkeypatch,
        plots,
        {
            "plot-a": [0.1, 0.0],
            "plot-b": [0.8, 0.2],
            "plot-c": [0.4, 0.4],
        },
    )

    r = client.get(
        "/api/reports/field-leaderboard?limit=1&offset=1"
        "&evaluationLimit=3&startDate=2026-05-01&endDate=2026-06-01"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["rankingScope"] == "all_filtered_fields"
    assert body["rows"][0]["rank"] == 2
    assert body["rows"][0]["plotId"] == "plot-c"
    assert body["rows"][0]["coordinates"] == [77.1, 12.1]
    assert body["rows"][0]["location"] == "12.1000, 77.1000"
    _assert_no_leaks(r.text)


def test_field_leaderboard_skips_unusable_points_and_reports_truncation(monkeypatch):
    plots = [_plot(f"plot-{idx}", f"Field {idx}") for idx in range(3)]
    _install_leaderboard_fakes(
        monkeypatch,
        plots,
        {
            "plot-0": [-999, 0.7, 0.5],
            "plot-1": [None, None, None],
            "plot-2": [0.9, 0.3],
        },
    )

    r = client.get(
        "/api/reports/field-leaderboard?evaluationLimit=2&limit=10"
        "&startDate=2026-05-01&endDate=2026-06-01"
    )

    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["truncated"] is True
    assert body["metadata"]["rankingScope"] == "first_N_filtered_fields"
    row0 = next(row for row in body["rows"] if row["plotId"] == "plot-0")
    assert row0["latestImageDate"] == "2026-05-20"
    missing = next(row for row in body["rows"] if row["plotId"] == "plot-1")
    assert missing["dataAvailable"] is False
    assert missing["rank"] is None
    assert body["metadata"]["weatherRiskAvailable"] is False
    assert body["metadata"]["weatherRiskSource"] == "pending"


def test_report_template_crud_and_invalid_column(monkeypatch):
    stored = {
        "id": "template-1",
        "name": "Ops",
        "columns": ["field", "latestIndexValue"],
        "filters": {"cropType": "Paddy"},
        "sort": {"sortBy": "score"},
        "createdAt": "2026-06-03T00:00:00Z",
        "updatedAt": "2026-06-03T00:00:00Z",
    }
    monkeypatch.setattr(reports.reports_repo, "create_report_template", lambda **_: stored)
    monkeypatch.setattr(reports.reports_repo, "list_report_templates", lambda *_: [stored])
    monkeypatch.setattr(reports.reports_repo, "get_report_template", lambda *_: stored)
    monkeypatch.setattr(
        reports.reports_repo,
        "update_report_template",
        lambda *_args, **_kwargs: {**stored, "name": "Updated"},
    )

    created = client.post(
        "/api/reports/templates",
        json={
            "name": "Ops",
            "columns": ["field", "latestIndexValue"],
            "filters": {"cropType": "Paddy"},
            "sort": {"sortBy": "score"},
        },
    )
    assert created.status_code == 201
    assert created.json()["id"] == "template-1"
    assert client.get("/api/reports/templates").json()[0]["name"] == "Ops"
    assert client.get("/api/reports/templates/template-1").json()["columns"] == [
        "field",
        "latestIndexValue",
    ]
    patched = client.patch("/api/reports/templates/template-1", json={"name": "Updated"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Updated"

    bad = client.post(
        "/api/reports/templates",
        json={"name": "Bad", "columns": ["unknownColumn"]},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_REPORT_COLUMN"


def test_field_leaderboard_csv_export_escapes_cells_and_uses_template(monkeypatch):
    _install_leaderboard_fakes(
        monkeypatch,
        [_plot("plot-1", "=Formula Field", groupName="+Group")],
        {"plot-1": [0.7, 0.2]},
    )
    monkeypatch.setattr(
        reports.reports_repo,
        "get_report_template",
        lambda *_: {
            "id": "template-1",
            "name": "CSV",
            "columns": ["field", "group", "latestIndexValue"],
            "filters": {},
            "sort": {},
            "createdAt": None,
            "updatedAt": None,
        },
    )

    r = client.get(
        "/api/reports/field-leaderboard/export.csv?templateId=template-1"
        "&startDate=2026-05-01&endDate=2026-06-01"
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "'=Formula Field" in r.text
    assert "'+Group" in r.text
    _assert_no_leaks(r.text)


def test_field_leaderboard_csv_export_validates_sort_and_evaluation_limit(monkeypatch):
    r_sort = client.get("/api/reports/field-leaderboard/export.csv?sortBy=unknownColumn")
    assert r_sort.status_code == 400
    assert r_sort.json()["error"]["code"] == "INVALID_SORT"
    _assert_no_leaks(r_sort.text)

    r_limit = client.get("/api/reports/field-leaderboard/export.csv?evaluationLimit=1000")
    assert r_limit.status_code == 400
    assert r_limit.json()["error"]["code"] == "INVALID_EVALUATION_LIMIT"
    _assert_no_leaks(r_limit.text)
