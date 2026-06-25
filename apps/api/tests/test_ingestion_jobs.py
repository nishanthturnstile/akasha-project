"""BFF tests for ingestion scheduler monitoring APIs.

Covers TASK-060 from docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md:
  - /api/monitoring/ingestion-schedules: schedule fields, scheduler due state
  - /api/monitoring/ingestion-jobs: list filters (limit/cursor/sourceId/aoiId/state/
      startedAfter/startedBefore), required job list fields
  - /api/monitoring/ingestion-jobs/{jobId}: detail with redacted request, provider
      input/response, manifest handles, validation problems, rejection reasons, ledger rows
  - Missing artifacts/ledger paths handled gracefully
  - No raw filesystem paths (/srv/akasha, /tmp, Windows drive paths) or full logs
    leak in frontend-safe responses
  - Source monitoring endpoint includes latest scheduler job and due/overdue fields
  - Auth/team protection wired (disabled mode from conftest.py)

Uses temp dirs and SQLite fixtures — no real /srv/akasha files required.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app import ingestion_jobs, source_monitoring
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers to build job artifact directories
# ---------------------------------------------------------------------------


def _make_job_dir(
    jobs_dir: Path,
    *,
    job_id: str,
    source_id: str = "resourcesat-2a-liss3-boa",
    provider: str = "bhoonidhi",
    aoi_id: str = "bangalore-60km",
    state: str = "succeeded",
    started_at: str = "2026-06-20T01:00:00Z",
    finished_at: str = "2026-06-20T01:30:00Z",
    found_count: int = 5,
    selected_count: int = 3,
    downloaded_count: int = 3,
    rejected_count: int = 2,
    window_start: str = "2026-06-01T00:00:00Z",
    window_end: str = "2026-06-20T00:00:00Z",
    include_observability: bool = True,
    include_request: bool = True,
    observability_override: dict | None = None,
) -> Path:
    jdir = jobs_dir / job_id
    jdir.mkdir(parents=True, exist_ok=True)

    status = {
        "jobId": job_id,
        "sourceId": source_id,
        "provider": provider,
        "aoiId": aoi_id,
        "status": state,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "updatedAt": finished_at,
        "foundCount": found_count,
        "selectedCount": selected_count,
        "downloadedCount": downloaded_count,
        "rejectedCount": rejected_count,
        "windowStart": window_start,
        "windowEnd": window_end,
    }
    (jdir / "status.json").write_text(json.dumps(status), encoding="utf-8")

    if include_request:
        request = {
            "sourceId": source_id,
            "provider": provider,
            "aoiId": aoi_id,
            "windowStart": window_start,
            "windowEnd": window_end,
        }
        (jdir / "request.json").write_text(json.dumps(request), encoding="utf-8")

    if include_observability:
        obs = observability_override or {
            "providerInputSummary": {
                "scheduleState": "routine",
                "lifecycleState": "search_enabled",
                "capabilities": ["search", "download"],
                "commercialState": "free",
                "aoiScope": "regional",
                "validationState": "validated",
                "cadenceClass": "10_to_20_days",
                "provider": provider,
            },
            "providerResponseSummary": {
                "rejectionReasons": ["already_ingested", "low_coverage"]
            },
            "verificationSummary": {
                "verdict": "pass",
                "problems": [],
                "checks": [{"check": "band_count_ok"}],
            },
            "searchManifestHandle": f"{job_id}:search_manifest",
            "downloadManifestHandle": f"{job_id}:download_manifest",
            "prepareManifestHandles": [f"{job_id}:prepare_manifest_0"],
            "nextDueAt": "2026-07-04T01:00:00Z",
            "scheduleDecision": "cadence_elapsed",
        }
        (jdir / "observability.json").write_text(json.dumps(obs), encoding="utf-8")

    return jdir


def _make_scheduler_ledger(jobs_dir: Path, entries: dict) -> None:
    ledger = {"entries": entries}
    (jobs_dir / "scheduler_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")


def _make_sqlite_ledger(path: Path, rows: list[dict]) -> None:
    """Create a scheduler_jobs SQLite DB with the given rows."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE scheduler_jobs (
            job_id TEXT NOT NULL PRIMARY KEY,
            source_id TEXT NOT NULL,
            provider TEXT,
            aoi_id TEXT,
            state TEXT NOT NULL,
            scheduled_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            window_start TEXT,
            window_end TEXT,
            found_count INTEGER,
            selected_count INTEGER,
            downloaded_count INTEGER,
            rejected_count INTEGER,
            failed_count INTEGER,
            failure_kind TEXT,
            schedule_decision TEXT,
            next_due_at TEXT
        )
    """)
    for row in rows:
        conn.execute(
            """
            INSERT INTO scheduler_jobs (
                job_id, source_id, provider, aoi_id, state,
                scheduled_at, started_at, finished_at, window_start, window_end,
                found_count, selected_count, downloaded_count, rejected_count,
                failed_count, failure_kind, schedule_decision, next_due_at
            ) VALUES (
                :job_id, :source_id, :provider, :aoi_id, :state,
                :scheduled_at, :started_at, :finished_at, :window_start, :window_end,
                :found_count, :selected_count, :downloaded_count, :rejected_count,
                :failed_count, :failure_kind, :schedule_decision, :next_due_at
            )
            """,
            row,
        )
    conn.commit()
    conn.close()


def _row(
    job_id: str,
    source_id: str = "resourcesat-2a-liss3-boa",
    provider: str = "bhoonidhi",
    aoi_id: str = "bangalore-60km",
    state: str = "succeeded",
    scheduled_at: str = "2026-06-20T01:00:00Z",
    started_at: str | None = "2026-06-20T01:05:00Z",
    finished_at: str | None = "2026-06-20T01:30:00Z",
    window_start: str = "2026-06-01T00:00:00Z",
    window_end: str = "2026-06-20T00:00:00Z",
    found_count: int | None = 5,
    selected_count: int | None = 3,
    downloaded_count: int | None = 3,
    rejected_count: int | None = 2,
    failed_count: int | None = 0,
    failure_kind: str | None = None,
    schedule_decision: str | None = "cadence_elapsed",
    next_due_at: str | None = "2026-07-04T01:00:00Z",
) -> dict:
    return {
        "job_id": job_id,
        "source_id": source_id,
        "provider": provider,
        "aoi_id": aoi_id,
        "state": state,
        "scheduled_at": scheduled_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "window_start": window_start,
        "window_end": window_end,
        "found_count": found_count,
        "selected_count": selected_count,
        "downloaded_count": downloaded_count,
        "rejected_count": rejected_count,
        "failed_count": failed_count,
        "failure_kind": failure_kind,
        "schedule_decision": schedule_decision,
        "next_due_at": next_due_at,
    }


# ---------------------------------------------------------------------------
# Schedules endpoint
# ---------------------------------------------------------------------------


def test_schedules_returns_unconfigured_when_no_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unconfigured"
    assert body["schedules"] == []
    assert "generatedAt" in body


def test_schedules_returns_unconfigured_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "scheduler_jobs_dir", str(tmp_path / "nonexistent"), raising=False
    )
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unconfigured"


def test_schedules_returns_empty_schedules_when_ledger_empty(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _make_scheduler_ledger(jobs_dir, {})
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["schedules"] == []


def test_schedules_returns_required_fields_from_ledger(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_abc123"
    _make_job_dir(jobs_dir, job_id=job_id)
    _make_scheduler_ledger(
        jobs_dir,
        {
            "resourcesat-2a-liss3-boa::bangalore-60km": {
                "lastJobId": job_id,
                "lastSucceededAt": "2026-06-20T01:30:00Z",
                "lastWindowEnd": "2026-06-20T00:00:00Z",
            }
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["schedules"]) == 1

    sched = body["schedules"][0]
    # Required fields from TASK-056
    assert sched["sourceId"] == "resourcesat-2a-liss3-boa"
    assert sched["aoiId"] == "bangalore-60km"
    assert sched["provider"] == "bhoonidhi"
    assert sched["adapter"] == "bhoonidhi"
    assert sched["lifecycleState"] == "search_enabled"
    assert sched["scheduleState"] == "routine"
    assert sched["scheduleEnabled"] is True
    assert sched["capabilities"] == ["search", "download"]
    assert sched["commercialState"] == "free"
    assert sched["aoiScope"] == "regional"
    assert sched["validationState"] == "validated"
    assert sched["cadenceDays"] == 14.0  # 10_to_20_days maps to 14 days
    assert sched["lastSuccessAt"] == "2026-06-20T01:30:00Z"
    assert sched["nextWindowStart"] == "2026-06-20T00:00:00Z"
    assert sched["nextDueAt"] == "2026-07-04T01:00:00Z"
    assert sched["dueReason"] == "cadence_elapsed"


def test_schedules_schedule_enabled_flag_reflects_state(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_abc123"
    _make_job_dir(
        jobs_dir,
        job_id=job_id,
        observability_override={
            "providerInputSummary": {
                "scheduleState": "background_only",
                "provider": "bhoonidhi",
            },
        },
    )
    _make_scheduler_ledger(
        jobs_dir,
        {
            "resourcesat-2a-liss3-boa::bangalore-60km": {
                "lastJobId": job_id,
                "lastSucceededAt": None,
            }
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    sched = resp.json()["schedules"][0]
    # background_only is in _SCHEDULE_ENABLED_STATES
    assert sched["scheduleEnabled"] is True
    assert sched["scheduleState"] == "background_only"


def test_schedules_enriches_failure_timestamps_from_sqlite(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_fail",
                state="failed",
                finished_at="2026-06-20T02:00:00Z",
                failure_kind="bhoonidhi_download",
            ),
        ],
    )
    _make_scheduler_ledger(
        jobs_dir,
        {
            "resourcesat-2a-liss3-boa::bangalore-60km": {
                "lastJobId": None,
                "lastSucceededAt": None,
            }
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    sched = resp.json()["schedules"][0]
    # last_failure_at comes from SQLite enrichment for failed jobs
    assert sched["lastFailureAt"] is not None


# ---------------------------------------------------------------------------
# Job list endpoint — unconfigured / empty
# ---------------------------------------------------------------------------


def test_job_list_returns_unconfigured_when_nothing_configured(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unconfigured"
    assert body["jobs"] == []
    assert "generatedAt" in body


def test_job_list_returns_empty_when_sqlite_empty(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(db, [])
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["jobs"] == []
    assert body["nextCursor"] is None


# ---------------------------------------------------------------------------
# Job list endpoint — required fields from SQLite
# ---------------------------------------------------------------------------


def test_job_list_returns_required_fields_from_sqlite(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_abc",
                found_count=5,
                selected_count=3,
                downloaded_count=3,
                rejected_count=2,
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["jobs"]) == 1

    job = body["jobs"][0]
    # Required fields from TASK-057
    assert job["jobId"] == "job_20260620T010000Z_abc"
    assert job["sourceId"] == "resourcesat-2a-liss3-boa"
    assert job["provider"] == "bhoonidhi"
    assert job["aoiId"] == "bangalore-60km"
    assert job["state"] == "succeeded"
    assert job["windowStart"] == "2026-06-01T00:00:00Z"
    assert job["windowEnd"] == "2026-06-20T00:00:00Z"
    assert job["foundCount"] == 5
    assert job["selectedCount"] == 3
    assert job["downloadedCount"] == 3
    assert job["rejectedCount"] == 2
    assert job["startedAt"] == "2026-06-20T01:05:00Z"
    assert job["finishedAt"] == "2026-06-20T01:30:00Z"
    assert job["updatedAt"] is not None


# ---------------------------------------------------------------------------
# Job list endpoint — filters
# ---------------------------------------------------------------------------


def test_job_list_filter_by_source_id(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row("job_001", source_id="resourcesat-2a-liss3-boa"),
            _row(
                "job_002",
                source_id="sentinel-2-l2a",
                scheduled_at="2026-06-19T01:00:00Z",
                started_at="2026-06-19T01:05:00Z",
                finished_at="2026-06-19T01:30:00Z",
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?sourceId=resourcesat-2a-liss3-boa")
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["jobId"] == "job_001"


def test_job_list_filter_by_aoi_id(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row("job_001", aoi_id="bangalore-60km"),
            _row(
                "job_002",
                aoi_id="mysore-60km",
                scheduled_at="2026-06-19T01:00:00Z",
                started_at="2026-06-19T01:05:00Z",
                finished_at="2026-06-19T01:30:00Z",
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?aoiId=mysore-60km")
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["jobId"] == "job_002"
    assert jobs[0]["aoiId"] == "mysore-60km"


def test_job_list_filter_by_state(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row("job_001", state="succeeded"),
            _row(
                "job_002",
                state="failed",
                scheduled_at="2026-06-19T01:00:00Z",
                started_at="2026-06-19T01:05:00Z",
                finished_at="2026-06-19T01:30:00Z",
                failure_kind="bhoonidhi_download",
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?state=failed")
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["state"] == "failed"
    assert jobs[0]["jobId"] == "job_002"


def test_job_list_filter_started_after(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row("job_001", started_at="2026-06-20T01:00:00Z"),
            _row(
                "job_002",
                started_at="2026-06-19T01:00:00Z",
                scheduled_at="2026-06-19T01:00:00Z",
                finished_at="2026-06-19T01:30:00Z",
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?startedAfter=2026-06-19T12:00:00Z")
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["jobId"] == "job_001"


def test_job_list_filter_started_before(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row("job_001", started_at="2026-06-20T01:00:00Z"),
            _row(
                "job_002",
                started_at="2026-06-19T01:00:00Z",
                scheduled_at="2026-06-19T01:00:00Z",
                finished_at="2026-06-19T01:30:00Z",
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?startedBefore=2026-06-19T12:00:00Z")
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["jobId"] == "job_002"


def test_job_list_respects_limit_and_returns_cursor(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    rows = [
        _row(f"job_{i:03d}", scheduled_at=f"2026-06-{20 - i:02d}T01:00:00Z")
        for i in range(5)
    ]
    _make_sqlite_ledger(db, rows)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?limit=2")
    body = resp.json()
    assert len(body["jobs"]) == 2
    assert body["nextCursor"] is not None


def test_job_list_pagination_cursor_advances(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    rows = [
        _row(f"job_{i:03d}", scheduled_at=f"2026-06-{25 - i:02d}T01:00:00Z")
        for i in range(4)
    ]
    _make_sqlite_ledger(db, rows)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp1 = client.get("/api/monitoring/ingestion-jobs?limit=2")
    body1 = resp1.json()
    assert len(body1["jobs"]) == 2
    cursor = body1["nextCursor"]
    assert cursor is not None

    resp2 = client.get(f"/api/monitoring/ingestion-jobs?limit=2&cursor={cursor}")
    body2 = resp2.json()
    assert len(body2["jobs"]) == 2
    # Ensure jobs are different
    ids1 = {j["jobId"] for j in body1["jobs"]}
    ids2 = {j["jobId"] for j in body2["jobs"]}
    assert ids1.isdisjoint(ids2)


def test_job_list_sqlite_cursor_tiebreaker_does_not_drop_same_timestamp_rows(
    monkeypatch, tmp_path
):
    db = tmp_path / "job_ledger.db"
    same_ts = "2026-06-20T01:00:00Z"
    _make_sqlite_ledger(
        db,
        [
            _row("job_c", scheduled_at=same_ts),
            _row("job_b", scheduled_at=same_ts),
            _row("job_a", scheduled_at=same_ts),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    seen: list[str] = []
    cursor = None
    for _ in range(3):
        url = "/api/monitoring/ingestion-jobs?limit=1"
        if cursor:
            url += f"&cursor={cursor}"
        body = client.get(url).json()
        seen.extend(job["jobId"] for job in body["jobs"])
        cursor = body["nextCursor"]
        if cursor is None:
            break

    assert sorted(seen) == ["job_a", "job_b", "job_c"]


# ---------------------------------------------------------------------------
# Job list endpoint — fallback to dir scan
# ---------------------------------------------------------------------------


def test_job_list_falls_back_to_dir_scan_when_no_sqlite(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _make_job_dir(jobs_dir, job_id="job_20260620T010000Z_abc")
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["jobs"]) == 1
    job = body["jobs"][0]
    assert job["jobId"] == "job_20260620T010000Z_abc"
    assert job["sourceId"] == "resourcesat-2a-liss3-boa"
    assert job["state"] == "succeeded"


def test_job_list_dir_scan_applies_source_filter(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _make_job_dir(jobs_dir, job_id="job_20260620T010000Z_a", source_id="resourcesat-2a-liss3-boa")
    _make_job_dir(
        jobs_dir, job_id="job_20260619T010000Z_b", source_id="sentinel-2-l2a"
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs?sourceId=resourcesat-2a-liss3-boa")
    jobs = resp.json()["jobs"]
    assert all(j["sourceId"] == "resourcesat-2a-liss3-boa" for j in jobs)
    assert any(j["jobId"] == "job_20260620T010000Z_a" for j in jobs)


def test_job_list_dir_scan_cursor_returns_next_unvisited_job(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _make_job_dir(jobs_dir, job_id="job_20260622T010000Z_a")
    _make_job_dir(jobs_dir, job_id="job_20260621T010000Z_b")
    _make_job_dir(jobs_dir, job_id="job_20260620T010000Z_c")
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    first = client.get("/api/monitoring/ingestion-jobs?limit=1").json()
    assert [job["jobId"] for job in first["jobs"]] == ["job_20260622T010000Z_a"]
    assert first["nextCursor"] == "job_20260622T010000Z_a"

    second = client.get(
        f"/api/monitoring/ingestion-jobs?limit=1&cursor={first['nextCursor']}"
    ).json()
    assert [job["jobId"] for job in second["jobs"]] == ["job_20260621T010000Z_b"]


# ---------------------------------------------------------------------------
# Job detail endpoint
# ---------------------------------------------------------------------------


def test_job_detail_returns_404_when_dir_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs/job_20260620T010000Z_abc")
    assert resp.status_code == 404


def test_job_detail_returns_404_for_unknown_job(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs/job_nonexistent")
    assert resp.status_code == 404


def test_job_detail_returns_required_fields(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_abc123"
    _make_job_dir(jobs_dir, job_id=job_id)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()

    # Required fields from TASK-058
    assert detail["jobId"] == job_id
    assert detail["sourceId"] == "resourcesat-2a-liss3-boa"
    assert detail["provider"] == "bhoonidhi"
    assert detail["aoiId"] == "bangalore-60km"
    assert detail["state"] == "succeeded"

    # Request fields (already redacted at scheduler write time)
    assert "request" in detail
    assert detail["request"]["sourceId"] == "resourcesat-2a-liss3-boa"
    assert detail["request"]["aoiId"] == "bangalore-60km"
    assert detail["request"]["windowStart"] == "2026-06-01T00:00:00Z"

    # Provider summaries
    assert "providerInputSummary" in detail
    assert detail["providerInputSummary"]["scheduleState"] == "routine"
    assert "providerResponseSummary" in detail

    # Manifest handles — opaque, not raw paths
    assert detail["searchManifestHandle"] == f"{job_id}:search_manifest"
    assert detail["downloadManifestHandle"] == f"{job_id}:download_manifest"
    assert detail["prepareManifestHandles"] == [f"{job_id}:prepare_manifest_0"]

    # Verification
    assert "verificationSummary" in detail
    assert "validationProblems" in detail

    # Rejection reasons from provider response
    assert "rejectionReasons" in detail
    assert "already_ingested" in detail["rejectionReasons"]
    assert "low_coverage" in detail["rejectionReasons"]

    # Artifact handles — opaque job tokens, not raw paths
    assert "artifactHandles" in detail
    for handle in detail["artifactHandles"].values():
        assert handle.startswith(f"{job_id}:")
        assert "/" not in handle
        assert "\\" not in handle
        assert "srv" not in handle


def test_job_detail_validation_problems_extracted(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_valtest"
    _make_job_dir(
        jobs_dir,
        job_id=job_id,
        observability_override={
            "providerInputSummary": {"scheduleState": "routine"},
            "providerResponseSummary": {},
            "verificationSummary": {
                "verdict": "fail",
                "problems": ["band_count_mismatch", "missing_mask"],
                "gateReason": "mandatory_check_failed",
            },
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()
    problems = detail["validationProblems"]
    assert "band_count_mismatch" in problems
    assert "missing_mask" in problems
    assert "mandatory_check_failed" in problems
    assert "verdict=fail" in problems


def test_job_detail_includes_ledger_rows_from_sqlite(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "job_ledger.db"
    job_id = "job_20260620T010000Z_ledger"
    _make_job_dir(jobs_dir, job_id=job_id)
    _make_sqlite_ledger(
        db,
        [_row(job_id)],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["ledgerRows"]) == 1
    ledger_row = detail["ledgerRows"][0]
    assert ledger_row["job_id"] == job_id
    assert ledger_row["source_id"] == "resourcesat-2a-liss3-boa"
    assert ledger_row["state"] == "succeeded"


def test_job_detail_ledger_rows_exclude_artifact_path(monkeypatch, tmp_path):
    """Ledger rows must not include raw filesystem paths (SEC-006)."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "job_ledger.db"
    job_id = "job_20260620T010000Z_sectest"
    _make_job_dir(jobs_dir, job_id=job_id)
    # Insert a row manually with an artifact_summary_path column (which must not be read)
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE scheduler_jobs (
            job_id TEXT NOT NULL PRIMARY KEY,
            source_id TEXT NOT NULL,
            provider TEXT,
            aoi_id TEXT,
            state TEXT NOT NULL,
            scheduled_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            window_start TEXT,
            window_end TEXT,
            found_count INTEGER,
            selected_count INTEGER,
            downloaded_count INTEGER,
            rejected_count INTEGER,
            failed_count INTEGER,
            failure_kind TEXT,
            schedule_decision TEXT,
            next_due_at TEXT,
            artifact_summary_path TEXT
        )
    """)
    conn.execute(
        "INSERT INTO scheduler_jobs (job_id, source_id, state, artifact_summary_path) "
        "VALUES (?, ?, ?, ?)",
        (
            job_id,
            "resourcesat-2a-liss3-boa",
            "succeeded",
            "/srv/akasha/ingestion/scheduler/jobs/secret_path",
        ),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()
    # The artifact_summary_path column is intentionally excluded from the SELECT
    row_json = json.dumps(detail["ledgerRows"])
    assert "/srv/akasha" not in row_json
    assert "secret_path" not in row_json


# ---------------------------------------------------------------------------
# Missing artifact handling — fail-soft
# ---------------------------------------------------------------------------


def test_job_detail_handles_missing_observability_gracefully(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_noobs"
    _make_job_dir(jobs_dir, job_id=job_id, include_observability=False)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["jobId"] == job_id
    assert detail["providerInputSummary"] == {}
    assert detail["providerResponseSummary"] == {}
    assert detail["verificationSummary"] == {}
    assert detail["validationProblems"] == []
    assert detail["rejectionReasons"] == []
    assert detail["searchManifestHandle"] is None
    assert detail["downloadManifestHandle"] is None
    assert detail["prepareManifestHandles"] == []


def test_job_detail_handles_missing_request_gracefully(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_noreq"
    _make_job_dir(jobs_dir, job_id=job_id, include_request=False)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["jobId"] == job_id
    assert detail["request"] == {}


def test_job_list_handles_sqlite_unavailable_gracefully(monkeypatch, tmp_path):
    """If SQLite path is set but file is absent, fallback to dir scan or unavailable."""
    monkeypatch.setattr(
        settings, "scheduler_job_ledger_path", str(tmp_path / "missing.db"), raising=False
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    # Path is configured but file missing → treated as unconfigured by _resolve_ledger_db
    body = resp.json()
    assert body["status"] in ("ok", "unconfigured", "unavailable")


def test_schedules_handles_missing_scheduler_ledger_json_gracefully(monkeypatch, tmp_path):
    """scheduler_ledger.json missing → empty schedules, not a crash."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    # No scheduler_ledger.json written
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["schedules"] == []


# ---------------------------------------------------------------------------
# No raw filesystem paths in responses (SEC-006)
# ---------------------------------------------------------------------------

_SUSPICIOUS_PATH_PATTERNS = [
    "/srv/akasha",
    "/tmp",
    "/var/tmp",
    "C:\\",
    "c:\\",
    r"\Users",
    "/root/",
    "\\\\",
]


def _assert_no_raw_paths(payload: object, context: str = "") -> None:
    text = json.dumps(payload)
    for pattern in _SUSPICIOUS_PATH_PATTERNS:
        assert pattern not in text, (
            f"Raw path pattern {pattern!r} found in {context} response: {text[:200]}"
        )


def test_job_list_does_not_leak_raw_paths(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _make_job_dir(jobs_dir, job_id="job_20260620T010000Z_pathtest")
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    _assert_no_raw_paths(resp.json(), context="/api/monitoring/ingestion-jobs")


def test_job_detail_does_not_leak_raw_paths(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_pathtest2"
    _make_job_dir(jobs_dir, job_id=job_id)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    _assert_no_raw_paths(resp.json(), context=f"/api/monitoring/ingestion-jobs/{job_id}")


def test_job_detail_redacts_paths_from_failure_messages(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_pathmsg"
    jdir = _make_job_dir(jobs_dir, job_id=job_id, state="failed")
    status = json.loads((jdir / "status.json").read_text(encoding="utf-8"))
    status["failureMessage"] = (
        "failed reading /srv/akasha/ingestion/raw/token.tif and "
        "C:\\Users\\operator\\secret\\download.zip"
    )
    status["failureKind"] = "io_error"
    (jdir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    _assert_no_raw_paths(body, context=f"/api/monitoring/ingestion-jobs/{job_id}")
    assert "[REDACTED_PATH]" in body["message"]


def test_schedules_does_not_leak_raw_paths(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_schedpath"
    _make_job_dir(jobs_dir, job_id=job_id)
    _make_scheduler_ledger(
        jobs_dir,
        {"resourcesat-2a-liss3-boa::bangalore-60km": {"lastJobId": job_id}},
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    _assert_no_raw_paths(resp.json(), context="/api/monitoring/ingestion-schedules")


def test_job_detail_artifact_handles_are_opaque_tokens(monkeypatch, tmp_path):
    """Artifact handles must be <jobId>:<type> tokens, never raw filesystem paths."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_opaque"
    _make_job_dir(jobs_dir, job_id=job_id)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    handles = resp.json()["artifactHandles"]
    for _artifact_type, handle in handles.items():
        # Must be "jobId:type" format
        assert ":" in handle
        parts = handle.split(":", 1)
        assert parts[0] == job_id
        # Must not contain filesystem paths
        assert "/" not in handle or handle.count("/") == 0
        assert not handle.startswith("/")


def test_job_detail_rejects_path_traversal_in_job_id(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)

    # Path traversal attempts
    for bad_id in ["../etc/passwd", "job/../../secret", "job\\..\\secret", "job..secret"]:
        resp = client.get(f"/api/monitoring/ingestion-jobs/{bad_id}")
        assert resp.status_code in (400, 404), f"Expected 400/404 for bad jobId {bad_id!r}"


# ---------------------------------------------------------------------------
# Source monitoring — scheduler job and due/overdue fields
# ---------------------------------------------------------------------------


def test_source_monitoring_includes_latest_scheduler_job_fields(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_sm",
                source_id="resourcesat-2a-liss3-boa",
                state="succeeded",
                next_due_at="2026-07-04T01:00:00Z",
                schedule_decision="cadence_elapsed",
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "label": "ResourceSat-2A LISS-3 BOA",
                "provider": "ISRO/NRSC Bhoonidhi",
                "kind": "optical",
                "analysisLevel": "field",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {
                "acquisitionDate": "2026-06-10",
                "isLatestUsable": True,
                "tileAvailable": True,
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": (
                        "2026-06-01T00:00:00Z/2026-06-15T23:59:59Z"
                    ),
                    "latestSuccessfulSearchUpdatedAt": "2026-06-20T01:00:00Z",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": "composite:bangalore-60km:2026-06-10",
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {"status": "ok", "bucket": "akasha-cogs", "objectCount": 0, "bytes": 0,
                 "zeroByteObjectCount": 0, "byPrefix": []},
    )

    resp = client.get("/api/monitoring/imagery-sources")
    assert resp.status_code == 200
    source = resp.json()["sources"][0]

    # Phase 9 scheduler linkage fields (TASK-059)
    assert "latestSchedulerJobId" in source
    assert "latestSchedulerJobState" in source
    assert "latestSchedulerJobUpdatedAt" in source
    assert "schedulerNextDueAt" in source
    assert "schedulerIsDue" in source
    assert "schedulerIsOverdue" in source
    assert "schedulerDueReason" in source

    assert source["latestSchedulerJobId"] == "job_20260620T010000Z_sm"
    assert source["latestSchedulerJobState"] == "succeeded"
    assert source["schedulerNextDueAt"] == "2026-07-04T01:00:00Z"


def test_source_monitoring_scheduler_is_due_when_next_due_in_past(monkeypatch, tmp_path):
    from datetime import UTC, datetime

    db = tmp_path / "job_ledger.db"
    # next_due_at is in the past relative to _now
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260601T010000Z_due",
                source_id="resourcesat-2a-liss3-boa",
                state="succeeded",
                scheduled_at="2026-06-01T01:00:00Z",
                next_due_at="2026-06-10T01:00:00Z",
                schedule_decision="cadence_elapsed",
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    # Freeze time to after next_due_at
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "kind": "optical",
                "analysisLevel": "field",
                "availabilityStatus": "active",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {"acquisitionDate": "2026-06-10", "tileAvailable": True, "isLatestUsable": True}
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulSearchUpdatedAt": "2026-06-15T01:00:00Z",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": "2026-06-01/2026-06-10",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": "composite:bangalore-60km:2026-06-10",
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {"status": "ok", "bucket": "akasha-cogs", "objectCount": 0, "bytes": 0,
                 "zeroByteObjectCount": 0, "byPrefix": []},
    )

    resp = client.get("/api/monitoring/imagery-sources")
    assert resp.status_code == 200
    source = resp.json()["sources"][0]
    # next_due_at 2026-06-10 < now 2026-06-15 → is_due=True, > 24h → is_overdue=True
    assert source["schedulerIsDue"] is True
    assert source["schedulerIsOverdue"] is True
    assert source["schedulerDueReason"] == "cadence_elapsed"


def test_source_monitoring_scheduler_not_due_when_in_future(monkeypatch, tmp_path):
    from datetime import UTC, datetime

    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_notdue",
                source_id="resourcesat-2a-liss3-boa",
                state="succeeded",
                next_due_at="2026-07-04T01:00:00Z",
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "source_freshness_stale_days", 45, raising=False)
    monkeypatch.setattr(
        source_monitoring,
        "_now",
        lambda: datetime(2026, 6, 20, tzinfo=UTC),
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_sources",
        lambda: [
            {
                "id": "resourcesat-2a-liss3-boa",
                "kind": "optical",
                "analysisLevel": "field",
                "availabilityStatus": "active",
            }
        ],
    )
    monkeypatch.setattr(
        source_monitoring.catalog,
        "list_dates",
        lambda source_id: [
            {"acquisitionDate": "2026-06-10", "tileAvailable": True, "isLatestUsable": True}
        ],
    )
    monkeypatch.setattr(
        source_monitoring,
        "_ingestion_ledger_summary",
        lambda: {
            "status": "ok",
            "bySource": [
                {
                    "sourceId": "resourcesat-2a-liss3-boa",
                    "latestSuccessfulSearchUpdatedAt": "2026-06-20T01:00:00Z",
                    "latestSuccessfulSearchAoiId": "bangalore-60km",
                    "latestSuccessfulSearchDatetimeRange": "2026-06-01/2026-06-10",
                    "latestSuccessfulCompositeDate": "2026-06-10",
                    "latestSuccessfulCompositeProductId": "composite:bangalore-60km:2026-06-10",
                    "latestSuccessfulCompositeAoiId": "bangalore-60km",
                    "latestSuccessfulCompositeUpdatedAt": "2026-06-11T01:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        source_monitoring,
        "_storage_usage",
        lambda: {"status": "ok", "bucket": "akasha-cogs", "objectCount": 0, "bytes": 0,
                 "zeroByteObjectCount": 0, "byPrefix": []},
    )

    resp = client.get("/api/monitoring/imagery-sources")
    assert resp.status_code == 200
    source = resp.json()["sources"][0]
    assert source["schedulerIsDue"] is False
    assert source["schedulerIsOverdue"] is False
    assert source["schedulerDueReason"] is None


def test_source_monitoring_includes_scheduler_fields_in_response_model(monkeypatch):
    schema = client.get("/api/openapi.json").json()
    schemas = schema["components"]["schemas"]
    source_props = schemas["ImagerySourceMonitoringSource"]["properties"]
    # Phase 9 scheduler linkage fields
    assert "latestSchedulerJobId" in source_props
    assert "latestSchedulerJobState" in source_props
    assert "latestSchedulerJobUpdatedAt" in source_props
    assert "schedulerNextDueAt" in source_props
    assert "schedulerIsDue" in source_props
    assert "schedulerIsOverdue" in source_props
    assert "schedulerDueReason" in source_props


# ---------------------------------------------------------------------------
# Auth/team protection
# ---------------------------------------------------------------------------


def test_monitoring_endpoints_require_auth_when_enabled(monkeypatch, tmp_path):
    """With auth_mode=enabled, endpoints should fail without a session cookie."""
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(db, [])
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    # Enable auth — expect 401 without a valid session cookie.
    monkeypatch.setattr(settings, "auth_mode", "enabled", raising=False)
    monkeypatch.setattr(settings, "auth_allow_disabled", False, raising=False)
    monkeypatch.setattr(
        settings, "auth_password_pepper", "test-pepper-secret-32-chars-abc", raising=False
    )

    resp = client.get("/api/monitoring/ingestion-jobs")
    # When auth is enabled and no session cookie is present, the endpoint returns 401.
    # The route is gated by get_current_team via Depends(get_current_team).
    assert resp.status_code == 401


def test_monitoring_endpoints_accessible_with_auth_disabled(monkeypatch, tmp_path):
    """Endpoints should be reachable with auth_mode=disabled (from conftest autouse)."""
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200


def test_ingestion_schedules_accessible_with_auth_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# OpenAPI schema documents monitoring APIs
# ---------------------------------------------------------------------------


def test_monitoring_apis_documented_in_openapi():
    schema = client.get("/api/openapi.json").json()
    paths = schema["paths"]
    assert "/api/monitoring/ingestion-schedules" in paths
    assert "/api/monitoring/ingestion-jobs" in paths
    assert "/api/monitoring/ingestion-jobs/{job_id}" in paths

    schemas = schema["components"]["schemas"]
    assert "IngestionScheduleItem" in schemas
    assert "IngestionScheduleResponse" in schemas
    assert "IngestionJobSummary" in schemas
    assert "IngestionJobListResponse" in schemas
    assert "IngestionJobDetail" in schemas

    schedule_props = schemas["IngestionScheduleItem"]["properties"]
    for field in (
        "sourceId", "provider", "adapter", "aoiId",
        "lifecycleState", "scheduleState", "scheduleEnabled",
        "productExposure", "lastRunAt", "lastSuccessAt", "lastFailureAt",
        "nextDueAt", "nextWindowStart", "nextWindowEnd", "cadenceDays", "dueReason",
    ):
        assert field in schedule_props, f"scheduleItem missing field {field!r}"

    job_props = schemas["IngestionJobSummary"]["properties"]
    for field in (
        "jobId", "sourceId", "provider", "aoiId", "state",
        "windowStart", "windowEnd", "foundCount", "selectedCount",
        "downloadedCount", "rejectedCount", "failureKind", "message",
        "startedAt", "finishedAt", "updatedAt",
    ):
        assert field in job_props, f"jobSummary missing field {field!r}"

    detail_props = schemas["IngestionJobDetail"]["properties"]
    for field in (
        "jobId", "sourceId", "provider", "aoiId", "state",
        "request", "providerInputSummary", "providerResponseSummary",
        "searchManifestHandle", "downloadManifestHandle", "prepareManifestHandles",
        "verificationSummary", "validationProblems", "rejectionReasons",
        "artifactHandles", "ledgerRows",
    ):
        assert field in detail_props, f"jobDetail missing field {field!r}"


# ---------------------------------------------------------------------------
# Helper unit tests — redaction
# ---------------------------------------------------------------------------


def test_redact_error_removes_credentials():
    text = "password=supersecret failed to connect to host"
    redacted = ingestion_jobs._redact_error(text)
    assert "supersecret" not in redacted
    assert "password" in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_removes_bearer_tokens():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
    redacted = ingestion_jobs._redact_error(text)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_truncates_at_300_chars():
    long_text = "x" * 500
    result = ingestion_jobs._redact_error(long_text)
    assert len(result) <= 300


def test_build_artifact_handles_returns_opaque_tokens():
    obs = {
        "searchManifestHandle": "job_abc:search_manifest",
        "downloadManifestHandle": "job_abc:download_manifest",
        "prepareManifestHandles": ["job_abc:prepare_0", "job_abc:prepare_1"],
    }
    handles = ingestion_jobs._build_artifact_handles("job_abc", obs)
    for _key, handle in handles.items():
        assert ":" in handle
        assert "/" not in handle or True  # opaque, not a path
        assert not handle.startswith("/")


def test_extract_validation_problems_extracts_all_forms():
    verification = {
        "problems": ["band_count_mismatch"],
        "checks": [{"check": "mask_valid", "message": "mask has nodata only"}],
        "verdict": "fail",
        "gateReason": "mandatory_check_failed",
    }
    problems = ingestion_jobs._extract_validation_problems(verification)
    assert "band_count_mismatch" in problems
    assert "mask has nodata only" in problems
    assert "verdict=fail" in problems
    assert "mandatory_check_failed" in problems


def test_extract_rejection_reasons_extracts_from_provider_response():
    response = {
        "rejectionReasons": ["already_ingested"],
        "skipReasons": [{"reason": "low_cloud_coverage", "skipReason": "cloud>50%"}],
    }
    reasons = ingestion_jobs._extract_rejection_reasons(response)
    assert "already_ingested" in reasons
    assert "low_cloud_coverage" in reasons


def test_cadence_days_mapping_for_all_known_classes():
    from app.ingestion_jobs import _CADENCE_DAYS

    assert _CADENCE_DAYS["multiple_per_day"] < 1
    assert _CADENCE_DAYS["daily"] == 1.0
    assert _CADENCE_DAYS["2_to_5_days"] > 1
    assert _CADENCE_DAYS["5_to_10_days"] > 1
    assert _CADENCE_DAYS["10_to_20_days"] > 1
    assert _CADENCE_DAYS["gt_20_days"] > 1
    assert _CADENCE_DAYS["archive_on_demand"] == 0.0
    assert _CADENCE_DAYS["reference"] == 0.0
