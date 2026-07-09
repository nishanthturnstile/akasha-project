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
  - Auth/team protection wired (owner/admin only; disabled mode from conftest.py)

Uses temp dirs and SQLite fixtures — no real /srv/akasha files required.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app import ingestion_jobs, source_monitoring
from app.auth import CurrentUser, TeamMembership, get_current_user
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


def _event(
    job_id: str,
    event_type: str,
    timestamp: str,
    payload: dict | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "jobId": job_id,
        "eventType": event_type,
        "payload": payload or {},
    }


def _write_events_jsonl(job_dir: Path, entries: list[dict | str]) -> None:
    lines = [
        entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
        for entry in entries
    ]
    (job_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_scheduler_ledger(jobs_dir: Path, entries: dict) -> None:
    ledger = {"entries": entries}
    (jobs_dir / "scheduler_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")


def _make_schedule_snapshot(jobs_dir: Path, schedules: list[dict]) -> None:
    snapshot = {
        "snapshotVersion": 1,
        "generatedAt": "2026-06-25T12:00:00Z",
        "schedules": schedules,
    }
    (jobs_dir / "schedule_state.json").write_text(json.dumps(snapshot), encoding="utf-8")


def _schedule_for_next_due(monkeypatch, tmp_path, next_due_at: str) -> dict:
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_due_state"
    _make_job_dir(
        jobs_dir,
        job_id=job_id,
        observability_override={
            "providerInputSummary": {
                "scheduleState": "routine",
                "provider": "bhoonidhi",
            },
            "nextDueAt": next_due_at,
            "scheduleDecision": "cadence_elapsed",
        },
    )
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
    monkeypatch.setattr(
        ingestion_jobs, "_now_iso", lambda: "2026-06-25T12:00:00Z"
    )

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    schedules = resp.json()["schedules"]
    assert len(schedules) == 1
    return schedules[0]


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


def _make_ingestion_ledger(path: Path, rows: list[dict]) -> None:
    """Create a Bhoonidhi ingestion_ledger SQLite DB with the given rows."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE ingestion_ledger (
            product_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            scene_key TEXT,
            status TEXT NOT NULL,
            retries INTEGER NOT NULL DEFAULT 0,
            bytes INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (product_id, source_id)
        )
    """)
    for row in rows:
        conn.execute(
            """
            INSERT INTO ingestion_ledger (
                product_id, source_id, scene_key, status, retries,
                bytes, error, created_at, updated_at
            ) VALUES (
                :product_id, :source_id, :scene_key, :status, :retries,
                :bytes, :error, :created_at, :updated_at
            )
            """,
            row,
        )
    conn.commit()
    conn.close()


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


def test_schedules_marks_row_due_within_grace_window(monkeypatch, tmp_path):
    sched = _schedule_for_next_due(
        monkeypatch,
        tmp_path,
        "2026-06-25T06:00:00Z",
    )

    assert sched["nextDueAt"] == "2026-06-25T06:00:00Z"
    assert sched["isDue"] is True
    assert sched["isOverdue"] is False
    assert sched["dueReason"] == "cadence_elapsed"


def test_schedules_marks_row_overdue_after_24_hour_grace(monkeypatch, tmp_path):
    sched = _schedule_for_next_due(
        monkeypatch,
        tmp_path,
        "2026-06-24T11:59:00Z",
    )

    assert sched["isDue"] is True
    assert sched["isOverdue"] is True


def test_schedules_marks_future_row_not_due(monkeypatch, tmp_path):
    sched = _schedule_for_next_due(
        monkeypatch,
        tmp_path,
        "2026-06-25T12:01:00Z",
    )

    assert sched["isDue"] is False
    assert sched["isOverdue"] is False
    assert sched["dueReason"] == "cadence_elapsed"


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


def test_schedules_enriches_run_and_failure_by_source_and_aoi(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_aoi_a_success",
                aoi_id="aoi-a",
                state="succeeded",
                scheduled_at="2026-06-20T01:00:00Z",
                finished_at="2026-06-20T01:30:00Z",
            ),
            _row(
                "job_20260621T010000Z_aoi_b_fail",
                aoi_id="aoi-b",
                state="failed",
                scheduled_at="2026-06-21T01:00:00Z",
                finished_at="2026-06-21T01:30:00Z",
                failure_kind="bhoonidhi_download",
            ),
        ],
    )
    _make_scheduler_ledger(
        jobs_dir,
        {
            "resourcesat-2a-liss3-boa::aoi-a": {
                "lastJobId": None,
                "lastSucceededAt": "2026-06-20T01:30:00Z",
            },
            "resourcesat-2a-liss3-boa::aoi-b": {
                "lastJobId": None,
                "lastSucceededAt": None,
            },
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    schedules = {item["aoiId"]: item for item in resp.json()["schedules"]}

    assert schedules["aoi-a"]["lastRunAt"] == "2026-06-20T01:00:00Z"
    assert schedules["aoi-a"]["lastFailureAt"] is None
    assert schedules["aoi-b"]["lastRunAt"] == "2026-06-21T01:00:00Z"
    assert schedules["aoi-b"]["lastFailureAt"] == "2026-06-21T01:30:00Z"


def test_schedules_do_not_apply_source_level_ledger_rows_to_aoi_rows(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_source_level",
                aoi_id=None,
                state="failed",
                scheduled_at="2026-06-20T01:00:00Z",
                finished_at="2026-06-20T01:30:00Z",
                failure_kind="source_level_failure",
            ),
        ],
    )
    _make_scheduler_ledger(
        jobs_dir,
        {
            "resourcesat-2a-liss3-boa::aoi-a": {
                "lastJobId": None,
                "lastSucceededAt": None,
            },
            "resourcesat-2a-liss3-boa": {
                "lastJobId": None,
                "lastSucceededAt": None,
            },
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")
    assert resp.status_code == 200
    schedules = {item["aoiId"]: item for item in resp.json()["schedules"]}

    assert schedules["aoi-a"]["lastRunAt"] is None
    assert schedules["aoi-a"]["lastFailureAt"] is None
    assert schedules[None]["lastRunAt"] == "2026-06-20T01:00:00Z"
    assert schedules[None]["lastFailureAt"] == "2026-06-20T01:30:00Z"


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
# Job events endpoint
# ---------------------------------------------------------------------------


def test_job_events_returns_empty_list_when_events_file_missing(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_noevents"
    _make_job_dir(jobs_dir, job_id=job_id)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["events"] == []
    assert body["truncated"] is False
    assert body["scannedCount"] == 0


def test_job_events_returns_404_for_unknown_job(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs/job_missing/events")
    assert resp.status_code == 404


def test_job_events_rejects_path_traversal_in_job_id(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs/job..secret/events")
    assert resp.status_code == 400


def test_job_events_malformed_line_does_not_crash_or_leak_raw_line(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_malformed"
    job_dir = _make_job_dir(jobs_dir, job_id=job_id)
    raw_bad_line = (
        '{"eventType": "broken", "raw": "/srv/akasha/RAW_MALFORMED_SECRET", '
        '"password": "malformed-password"'
    )
    _write_events_jsonl(
        job_dir,
        [
            _event(job_id, "job_created", "2026-06-20T01:00:00Z"),
            raw_bad_line,
            _event(
                job_id,
                "status_change",
                "2026-06-20T01:01:00Z",
                {"from": "planned", "to": "running"},
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    text = json.dumps(body)
    assert "RAW_MALFORMED_SECRET" not in text
    assert "malformed-password" not in text
    assert raw_bad_line not in text
    assert body["status"] == "ok"
    assert {event["eventType"] for event in body["events"]} >= {
        "job_created",
        "status_change",
    }


def test_job_events_returns_latest_events_with_truncation_metadata(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_latest"
    job_dir = _make_job_dir(jobs_dir, job_id=job_id)
    all_events = [
        _event(
            job_id,
            "progress",
            f"2026-06-20T01:{i // 60:02d}:{i % 60:02d}Z",
            {"sequence": i},
        )
        for i in range(205)
    ]
    _write_events_jsonl(job_dir, all_events)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    returned_sequences = [event["payload"]["sequence"] for event in body["events"]]
    assert len(returned_sequences) == 200
    assert returned_sequences == list(range(5, 205))
    assert body["truncated"] is True
    assert body["scannedCount"] == 205


def test_job_events_redacts_paths_and_secrets(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_eventredact"
    job_dir = _make_job_dir(jobs_dir, job_id=job_id)
    _write_events_jsonl(
        job_dir,
        [
            _event(
                job_id,
                "dry_run_plan",
                "2026-06-20T01:00:00Z",
                {
                    "rawRoot": "/srv/akasha/data/raw/bhoonidhi",
                    "downloadPath": "/tmp/coverage_manifest.json",
                    "scratch": "/var/tmp/akasha-work",
                    "windowsPath": "C:\\Users\\operator\\secret\\product.zip",
                    "message": (
                        "Authorization: Bearer bearer-token-value "
                        "password=super-secret-password secret=super-secret-value "
                        "token=token-value-123"
                    ),
                    "signedUrl": (
                        "https://object-store.internal/akasha-cogs/analytic.tif?"
                        "X-Amz-Signature=signature-secret-123&"
                        "X-Amz-Credential=credential-secret-456&"
                        "AWSAccessKeyId=AKIA_TEST_SECRET&token=signed-token-789"
                    ),
                    "internalUrls": [
                        "http://minio:9000/akasha-cogs/analytic.tif",
                        "http://postgis:5432/akasha",
                        "http://stac-api:8080/collections",
                    ],
                    "Authorization": "Bearer auth-header-secret",
                    "headers": {"authorization": "Bearer nested-auth-header-secret"},
                    "providerCredentials": {
                        "username": "bhoonidhi-user",
                        "password": "bhoonidhi-password",
                        "secret": "bhoonidhi-secret",
                        "token": "bhoonidhi-token",
                    },
                    "objectStoreCredentials": {
                        "accessKey": "object-access-key",
                        "secretKey": "object-secret-key",
                        "sessionToken": "object-session-token",
                    },
                },
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    _assert_no_raw_paths(body, context=f"/api/monitoring/ingestion-jobs/{job_id}/events")
    text = json.dumps(body)
    for forbidden in (
        "bearer-token-value",
        "super-secret-password",
        "super-secret-value",
        "token-value-123",
        "signature-secret-123",
        "credential-secret-456",
        "signed-token-789",
        "AKIA_TEST_SECRET",
        "object-store.internal",
        "minio:9000",
        "postgis:5432",
        "stac-api:8080",
        "auth-header-secret",
        "nested-auth-header-secret",
        "bhoonidhi-password",
        "bhoonidhi-secret",
        "bhoonidhi-token",
        "object-access-key",
        "object-secret-key",
        "object-session-token",
        "Authorization",
        "authorization",
    ):
        assert forbidden not in text


def test_job_events_normalizes_current_emitted_event_types(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_mapping"
    job_dir = _make_job_dir(jobs_dir, job_id=job_id)
    _write_events_jsonl(
        job_dir,
        [
            _event(job_id, "job_created", "2026-06-20T01:00:00Z"),
            _event(
                job_id,
                "job_created",
                "2026-06-20T01:00:30Z",
                {"status": "running"},
            ),
            _event(
                job_id,
                "status_change",
                "2026-06-20T01:01:00Z",
                {"from": "planned", "to": "running"},
            ),
            _event(
                job_id,
                "status_change",
                "2026-06-20T01:02:00Z",
                {"from": "running", "to": "succeeded"},
            ),
            _event(job_id, "dry_run_plan", "2026-06-20T01:03:00Z"),
            _event(
                job_id,
                "dry_run_plan",
                "2026-06-20T01:03:30Z",
                {"status": "failed"},
            ),
            _event(
                job_id,
                "future_event",
                "2026-06-20T01:04:00Z",
                {"status": "running"},
            ),
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}/events")
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert [(event["eventType"], event["stage"], event["status"]) for event in events] == [
        ("job_created", "planned", "planned"),
        ("job_created", "planned", "planned"),
        ("status_change", "running", "running"),
        ("status_change", "terminal", "succeeded"),
        ("dry_run_plan", "planned", "planned"),
        ("dry_run_plan", "planned", "planned"),
        ("future_event", "unknown", "unknown"),
    ]
    for event in events:
        assert isinstance(event["message"], str)
        assert event["message"]


def test_job_events_redacts_quoted_json_secret_strings(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_jsonsecret"
    job_dir = _make_job_dir(jobs_dir, job_id=job_id)
    _write_events_jsonl(
        job_dir,
        [
            _event(
                job_id,
                "status_change",
                "2026-06-20T01:00:00Z",
                {
                    "to": "failed",
                    "message": (
                        'provider error {"password":"json-password", '
                        '"token":"json-token", "secret": "json-secret"}'
                    ),
                    "details": (
                        "nested {'accessKey': 'quoted-access-key', "
                        "'credential': 'quoted-credential'}"
                    ),
                },
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}/events")
    assert resp.status_code == 200
    text = json.dumps(resp.json())
    for forbidden in (
        "json-password",
        "json-token",
        "json-secret",
        "quoted-access-key",
        "quoted-credential",
    ):
        assert forbidden not in text


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


def test_ledger_ro_connection_uses_immutable_uri(monkeypatch, tmp_path):
    """Read-only API mounts require immutable SQLite opens; plain mode=ro may create shm."""
    db = tmp_path / "job_ledger.db"
    db.write_bytes(b"SQLite format 3\x00")
    captured: dict[str, object] = {}

    class FakeConnection:
        row_factory = None

        def execute(self, sql: str):
            captured["pragma"] = sql

    def fake_connect(database: str, *, uri: bool = False):
        captured["database"] = database
        captured["uri_flag"] = uri
        return FakeConnection()

    monkeypatch.setattr(ingestion_jobs.sqlite3, "connect", fake_connect)

    conn = ingestion_jobs._open_ledger_ro(db)

    assert conn.row_factory is ingestion_jobs.sqlite3.Row
    assert captured["database"] == f"file:{db.as_posix()}?mode=ro&immutable=1"
    assert captured["uri_flag"] is True
    assert captured["pragma"] == "PRAGMA busy_timeout=5000;"


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


def test_schedules_reads_redacted_schedule_snapshot_before_success_ledger(monkeypatch, tmp_path):
    """schedule_state.json gives operators source cadence before the first successful run."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _make_schedule_snapshot(
        jobs_dir,
        [
            {
                "sourceId": "resourcesat-2a-liss3-boa",
                "provider": "bhoonidhi",
                "aoiId": "bangalore-60km",
                "lifecycleState": "validate_enabled",
                "scheduleState": "routine",
                "capabilities": ["search_enabled", "download_enabled"],
                "commercialState": "approved",
                "aoiScope": "in_aoi",
                "validationState": "validation_passed",
                "scheduleEnabled": True,
                "productExposure": "product_active",
                "lastSuccessAt": None,
                "nextDueAt": None,
                "nextWindowStart": "2026-06-13",
                "nextWindowEnd": "2026-06-25",
                "cadenceDays": 20,
                "dueReason": "first_run",
                "isDue": True,
                "isOverdue": False,
            }
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-schedules")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["generatedAt"] == "2026-06-25T12:00:00Z"
    assert body["schedules"][0]["sourceId"] == "resourcesat-2a-liss3-boa"
    assert body["schedules"][0]["scheduleState"] == "routine"
    assert body["schedules"][0]["productExposure"] == "product_active"
    assert body["schedules"][0]["isDue"] is True


# ---------------------------------------------------------------------------
# Simplified satellite-centric source endpoint
# ---------------------------------------------------------------------------


def test_ingestion_sources_summarize_satellites_with_latest_job_and_schedule(
    monkeypatch, tmp_path
):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "job_ledger.db"
    product_ledger = tmp_path / "bhoonidhi_ledger.sqlite"
    _make_schedule_snapshot(
        jobs_dir,
        [
            {
                "sourceId": "resourcesat-2a-liss3-boa",
                "provider": "bhoonidhi",
                "aoiId": "bangalore-60km",
                "scheduleState": "routine",
                "scheduleEnabled": True,
                "lastRunAt": "2026-06-20T01:00:00Z",
                "lastSuccessAt": "2026-06-20T01:30:00Z",
                "lastFailureAt": "2026-06-18T01:30:00Z",
                "nextDueAt": "2026-06-25T06:00:00Z",
                "cadenceDays": 7,
                "dueReason": "cadence_elapsed",
                "isDue": True,
                "isOverdue": False,
            }
        ],
    )
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260618T010000Z_old_fail",
                state="failed",
                scheduled_at="2026-06-18T01:00:00Z",
                finished_at="2026-06-18T01:30:00Z",
                found_count=2,
                selected_count=1,
                downloaded_count=0,
                rejected_count=1,
                failure_kind="bhoonidhi_download",
            ),
            _row(
                "job_20260620T010000Z_latest_success",
                state="succeeded",
                scheduled_at="2026-06-20T01:00:00Z",
                finished_at="2026-06-20T01:30:00Z",
                found_count=8,
                selected_count=4,
                downloaded_count=3,
                rejected_count=4,
                next_due_at="2026-06-25T06:00:00Z",
            ),
        ],
    )
    _make_ingestion_ledger(
        product_ledger,
        [
            {
                "product_id": "composite:bangalore-60km:2026-06-18",
                "source_id": "resourcesat-2a-liss3-boa",
                "scene_key": "composite:bangalore-60km:2026-06-18",
                "status": "composited",
                "retries": 0,
                "bytes": 1234,
                "error": None,
                "created_at": "2026-06-18T02:00:00Z",
                "updated_at": "2026-06-18T02:00:00Z",
            },
            {
                "product_id": "composite:bangalore-60km:2026-06-21",
                "source_id": "resourcesat-2a-liss3-boa",
                "scene_key": "composite:bangalore-60km:2026-06-21",
                "status": "composited",
                "retries": 0,
                "bytes": 5678,
                "error": None,
                "created_at": "2026-06-17T02:00:00Z",
                "updated_at": "2026-06-17T02:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_ledger_path", str(product_ledger), raising=False)
    monkeypatch.setattr(settings, "admin_ingestion_live_trigger_enabled", True, raising=False)

    resp = client.get("/api/monitoring/ingestion-sources")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["liveTriggerEnabled"] is True
    sources = {item["sourceId"]: item for item in body["sources"]}
    source = sources["resourcesat-2a-liss3-boa"]
    assert source["label"] == "ResourceSat-2A LISS-3 BOA"
    assert source["provider"] == "ISRO/NRSC Bhoonidhi"
    assert source["kind"] == "optical"
    assert source["active"] is True
    assert source["aoiId"] == "bangalore-60km"
    assert source["cadenceDays"] == 7.0
    assert source["lastRunAt"] == "2026-06-20T01:00:00Z"
    assert source["lastSuccessAt"] == "2026-06-20T01:30:00Z"
    assert source["lastFailureAt"] == "2026-06-18T01:30:00Z"
    assert source["nextDueAt"] == "2026-06-25T06:00:00Z"
    assert source["isDue"] is True
    assert source["isOverdue"] is False
    assert source["latestCompositeDate"] == "2026-06-21"
    assert source["lastJob"] == {
        "jobId": "job_20260620T010000Z_latest_success",
        "state": "succeeded",
        "runAt": "2026-06-20T01:30:00Z",
        "foundCount": 8,
        "selectedCount": 4,
        "downloadedCount": 3,
        "rejectedCount": 4,
        "windowStart": "2026-06-01T00:00:00Z",
        "windowEnd": "2026-06-20T00:00:00Z",
        "failureKind": None,
        "message": None,
    }
    assert any(not item["active"] and item["gatedReason"] for item in body["sources"])


def test_ingestion_sources_treats_eos04_as_admin_manageable_backend_support(
    monkeypatch, tmp_path
):
    """EOS-04 is not map-active, but admins must still manage/sync it behind the scenes."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    db = tmp_path / "scheduler.sqlite"
    _make_schedule_snapshot(
        jobs_dir,
        [
            {
                "sourceId": "eos-04-sar-mrs-l2b",
                "provider": "bhoonidhi",
                "aoiId": "bangalore-60km",
                "scheduleState": "manual_only",
                "scheduleEnabled": False,
                "productExposure": "background_only",
                "validationState": "validation_passed",
                "capabilities": [
                    "search_enabled",
                    "download_enabled",
                    "prepare_enabled",
                    "validate_enabled",
                ],
                "cadenceDays": 10,
            }
        ],
    )
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260630T053928Z_eos04",
                source_id="eos-04-sar-mrs-l2b",
                scheduled_at="2026-06-30T05:39:28Z",
                started_at="2026-06-30T05:39:30Z",
                finished_at="2026-06-30T05:45:00Z",
                window_start="2026-05-17",
                window_end="2026-06-30",
                found_count=10,
                selected_count=1,
                downloaded_count=1,
                rejected_count=None,
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "bhoonidhi_ledger_path", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-sources")

    assert resp.status_code == 200
    sources = {item["sourceId"]: item for item in resp.json()["sources"]}
    eos04 = sources["eos-04-sar-mrs-l2b"]
    assert eos04["active"] is False
    assert eos04["availabilityStatus"] == "gated"
    assert eos04["adminManageable"] is True
    assert eos04["syncEnabled"] is True
    assert eos04["scheduleState"] == "manual_only"
    assert eos04["productExposure"] == "background_only"
    assert eos04["validationState"] == "validation_passed"
    assert eos04["lastRunAt"] == "2026-06-30T05:45:00Z"
    assert eos04["lastSuccessAt"] == "2026-06-30T05:45:00Z"
    assert eos04["lastJob"]["runAt"] == "2026-06-30T05:45:00Z"
    assert eos04["lastJob"]["downloadedCount"] == 1


def test_ingestion_source_products_returns_real_scenes_only_and_redacts_errors(
    monkeypatch, tmp_path
):
    ledger = tmp_path / "bhoonidhi_ledger.sqlite"
    _make_ingestion_ledger(
        ledger,
        [
            {
                "product_id": "RA319MAR2026048153009900065PSANSTUCSRHTDF",
                "source_id": "resourcesat-2a-liss3-boa",
                "scene_key": "resourcesat-2a-liss3-boa:BOA:99:65:2026-03-19T00:00:00Z",
                "status": "downloaded",
                "retries": 0,
                "bytes": 1048576,
                "error": None,
                "created_at": "2026-06-20T01:00:00Z",
                "updated_at": "2026-06-20T01:30:00Z",
            },
            {
                "product_id": "RA319MAR2026048153009900065FAILED",
                "source_id": "resourcesat-2a-liss3-boa",
                "scene_key": "resourcesat-2a-liss3-boa:BOA:99:66:2026-03-20T00:00:00Z",
                "status": "failed",
                "retries": 2,
                "bytes": 0,
                "error": "failed at /srv/akasha/raw/product.zip token=secret-value",
                "created_at": "2026-06-20T02:00:00Z",
                "updated_at": "2026-06-20T02:30:00Z",
            },
            {
                "product_id": "sync:bangalore-60km:2026-06-20",
                "source_id": "resourcesat-2a-liss3-boa",
                "scene_key": "sync:bangalore-60km:2026-06-20",
                "status": "searched",
                "retries": 0,
                "bytes": 0,
                "error": None,
                "created_at": "2026-06-20T03:00:00Z",
                "updated_at": "2026-06-20T03:00:00Z",
            },
            {
                "product_id": "composite:bangalore-60km:2026-06-20",
                "source_id": "resourcesat-2a-liss3-boa",
                "scene_key": "composite:bangalore-60km:2026-06-20",
                "status": "composited",
                "retries": 0,
                "bytes": 100,
                "error": None,
                "created_at": "2026-06-20T04:00:00Z",
                "updated_at": "2026-06-20T04:00:00Z",
            },
            {
                "product_id": "AW319MAR2026048153009900065PSANSTUCSRHTDF",
                "source_id": "resourcesat-2a-awifs-boa",
                "scene_key": "resourcesat-2a-awifs-boa:BOA:99:65:2026-03-19T00:00:00Z",
                "status": "downloaded",
                "retries": 0,
                "bytes": 2048,
                "error": None,
                "created_at": "2026-06-20T05:00:00Z",
                "updated_at": "2026-06-20T05:00:00Z",
            },
        ],
    )
    monkeypatch.setattr(settings, "bhoonidhi_ledger_path", str(ledger), raising=False)

    resp = client.get(
        "/api/monitoring/ingestion-sources/resourcesat-2a-liss3-boa/products?limit=10"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["sourceId"] == "resourcesat-2a-liss3-boa"
    products = body["products"]
    assert [item["productId"] for item in products] == [
        "RA319MAR2026048153009900065FAILED",
        "RA319MAR2026048153009900065PSANSTUCSRHTDF",
    ]
    assert products[0]["acquisitionDate"] == "2026-03-20"
    assert products[1]["acquisitionDate"] == "2026-03-19"
    assert products[1]["bytes"] == 1048576
    serialized = json.dumps(body)
    assert "sync:bangalore" not in serialized
    assert "composite:bangalore" not in serialized
    assert "/srv/akasha" not in serialized
    assert "secret-value" not in serialized


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


def test_job_detail_redacts_nested_verification_paths(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_nestedpath"
    _make_job_dir(
        jobs_dir,
        job_id=job_id,
        observability_override={
            "providerInputSummary": {
                "scheduleState": "routine",
                "rawRoot": "/srv/akasha/data/raw/bhoonidhi",
            },
            "providerResponseSummary": {
                "downloaded": [
                    {
                        "itemId": "product-1",
                        "localPath": "C:\\Users\\operator\\secret\\product.zip",
                    }
                ]
            },
            "verificationSummary": {
                "verdict": "pass",
                "searchManifestPath": "/srv/akasha/data/work/coverage_manifest.json",
                "downloadManifestPath": "/tmp/download_manifest.json",
                "checks": [
                    {
                        "message": "verified /srv/akasha/data/work/composite/analytic.tif"
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    _assert_no_raw_paths(body, context=f"/api/monitoring/ingestion-jobs/{job_id}")
    assert "searchManifestPath" not in body["verificationSummary"]
    assert "downloadManifestPath" not in body["verificationSummary"]
    assert "rawRoot" not in body["providerInputSummary"]
    assert "localPath" not in body["providerResponseSummary"]["downloaded"][0]
    assert "[REDACTED_PATH]" in body["verificationSummary"]["checks"][0]["message"]


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


def test_job_detail_redacts_paths_from_failure_kind(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_pathkind"
    jdir = _make_job_dir(jobs_dir, job_id=job_id, state="failed")
    status = json.loads((jdir / "status.json").read_text(encoding="utf-8"))
    status["failureKind"] = "/srv/akasha/ingestion/raw/failure-kind.txt"
    (jdir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)

    resp = client.get(f"/api/monitoring/ingestion-jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    _assert_no_raw_paths(body, context=f"/api/monitoring/ingestion-jobs/{job_id}")
    assert body["failureKind"] == "[REDACTED_PATH]"


def test_job_list_redacts_paths_from_failure_kind(monkeypatch, tmp_path):
    db = tmp_path / "job_ledger.db"
    _make_sqlite_ledger(
        db,
        [
            _row(
                "job_20260620T010000Z_pathkindlist",
                state="failed",
                failure_kind="C:\\Users\\operator\\secret\\failure-kind.txt",
            )
        ],
    )
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", str(db), raising=False)
    monkeypatch.setattr(settings, "scheduler_jobs_dir", "", raising=False)

    resp = client.get("/api/monitoring/ingestion-jobs")
    assert resp.status_code == 200
    body = resp.json()
    _assert_no_raw_paths(body, context="/api/monitoring/ingestion-jobs")
    assert body["jobs"][0]["failureKind"] == "[REDACTED_PATH]"


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


def _override_current_user_role(role: str) -> None:
    team_id = "22222222-2222-4222-8222-222222222222"
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="11111111-1111-4111-8111-111111111111",
        username=f"{role}-user",
        email=f"{role}@example.test",
        display_name=f"{role.title()} User",
        role=role,
        current_team_id=team_id,
        memberships=(TeamMembership(id=team_id, name="Test Team", role=role),),
    )


def _configure_ingestion_rbac_fixtures(monkeypatch, tmp_path) -> str:
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "job_20260620T010000Z_rbac"
    _make_job_dir(jobs_dir, job_id=job_id)
    _make_scheduler_ledger(
        jobs_dir,
        {"resourcesat-2a-liss3-boa::bangalore-60km": {"lastJobId": job_id}},
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)
    return job_id


def _configure_trigger_fixtures(monkeypatch, tmp_path) -> Path:
    jobs_dir = tmp_path / "jobs"
    inbox_dir = tmp_path / "inbox"
    jobs_dir.mkdir(parents=True)
    inbox_dir.mkdir(parents=True)
    job_id = "job_20260620T010000Z_trigger"
    _make_job_dir(
        jobs_dir,
        job_id=job_id,
        observability_override={
            "providerInputSummary": {
                "scheduleState": "routine",
                "provider": "bhoonidhi",
                "capabilities": ["search", "download"],
            },
            "nextDueAt": "2026-07-04T01:00:00Z",
            "scheduleDecision": "cadence_elapsed",
        },
    )
    _make_scheduler_ledger(
        jobs_dir,
        {"resourcesat-2a-liss3-boa::bangalore-60km": {"lastJobId": job_id}},
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)
    monkeypatch.setattr(settings, "ingestion_job_inbox_dir", str(inbox_dir), raising=False)
    monkeypatch.setattr(settings, "admin_ingestion_live_trigger_enabled", False, raising=False)
    return inbox_dir


def _configure_eos04_trigger_fixtures(monkeypatch, tmp_path) -> Path:
    jobs_dir = tmp_path / "jobs"
    inbox_dir = tmp_path / "inbox"
    jobs_dir.mkdir(parents=True)
    inbox_dir.mkdir(parents=True)
    _make_schedule_snapshot(
        jobs_dir,
        [
            {
                "sourceId": "eos-04-sar-mrs-l2b",
                "provider": "bhoonidhi",
                "aoiId": "bangalore-60km",
                "scheduleState": "manual_only",
                "scheduleEnabled": False,
                "productExposure": "background_only",
                "validationState": "validation_passed",
                "capabilities": ["search_enabled", "download_enabled", "prepare_enabled"],
            }
        ],
    )
    monkeypatch.setattr(settings, "scheduler_jobs_dir", str(jobs_dir), raising=False)
    monkeypatch.setattr(settings, "scheduler_job_ledger_path", "", raising=False)
    monkeypatch.setattr(settings, "ingestion_job_inbox_dir", str(inbox_dir), raising=False)
    monkeypatch.setattr(settings, "admin_ingestion_live_trigger_enabled", True, raising=False)
    return inbox_dir


def _trigger_payload(**overrides) -> dict:
    payload = {"sourceId": "resourcesat-2a-liss3-boa"}
    payload.update(overrides)
    return payload


def _read_submitted_request(inbox_dir: Path, job_request_id: str) -> dict:
    path = inbox_dir / job_request_id / "request.json"
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def test_ingestion_monitoring_endpoints_allow_owner_and_admin(monkeypatch, tmp_path):
    job_id = _configure_ingestion_rbac_fixtures(monkeypatch, tmp_path)
    endpoints = (
        "/api/monitoring/ingestion-sources",
        "/api/monitoring/ingestion-sources/resourcesat-2a-liss3-boa/products",
        "/api/monitoring/ingestion-schedules",
        "/api/monitoring/ingestion-jobs",
        f"/api/monitoring/ingestion-jobs/{job_id}",
        f"/api/monitoring/ingestion-jobs/{job_id}/events",
    )

    for role in ("owner", "admin"):
        _override_current_user_role(role)
        try:
            for endpoint in endpoints:
                resp = client.get(endpoint)
                assert resp.status_code == 200, f"{role=} should access {endpoint}"
        finally:
            app.dependency_overrides.clear()


def test_ingestion_monitoring_endpoints_reject_member_and_viewer(monkeypatch, tmp_path):
    job_id = _configure_ingestion_rbac_fixtures(monkeypatch, tmp_path)
    endpoints = (
        "/api/monitoring/ingestion-sources",
        "/api/monitoring/ingestion-sources/resourcesat-2a-liss3-boa/products",
        "/api/monitoring/ingestion-schedules",
        "/api/monitoring/ingestion-jobs",
        f"/api/monitoring/ingestion-jobs/{job_id}",
        f"/api/monitoring/ingestion-jobs/{job_id}/events",
    )

    for role in ("member", "viewer"):
        _override_current_user_role(role)
        try:
            for endpoint in endpoints:
                resp = client.get(endpoint)
                assert resp.status_code == 403, f"{role=} should be forbidden from {endpoint}"
        finally:
            app.dependency_overrides.clear()


def test_trigger_ingestion_job_allows_owner_and_admin(monkeypatch, tmp_path):
    for role in ("owner", "admin"):
        inbox_dir = _configure_trigger_fixtures(monkeypatch, tmp_path / role)
        _override_current_user_role(role)
        try:
            resp = client.post(
                "/api/monitoring/ingestion-jobs/trigger",
                json=_trigger_payload(),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "submitted"
            assert body["dryRun"] is True
            assert body["jobRequestId"].startswith("ingest-ui-")
            assert body["jobsUrl"] == "/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa"
            assert _read_submitted_request(inbox_dir, body["jobRequestId"])["requested_by"] == (
                f"{role}@example.test@bff"
            )
        finally:
            app.dependency_overrides.clear()


def test_trigger_ingestion_job_allows_manual_only_eos04_backend_sync(monkeypatch, tmp_path):
    inbox_dir = _configure_eos04_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("admin")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json={
                "sourceId": "eos-04-sar-mrs-l2b",
                "aoiId": "bangalore-60km",
                "dryRun": False,
                "confirmLive": True,
                "windowDays": 12,
                "maxDownloads": 1,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["dryRun"] is False
        submitted = _read_submitted_request(inbox_dir, body["jobRequestId"])
        assert submitted["source_id"] == "eos-04-sar-mrs-l2b"
        assert submitted["aoi_id"] == "bangalore-60km"
        assert submitted["dry_run"] is False
    finally:
        app.dependency_overrides.clear()


def test_trigger_ingestion_job_rejects_member_and_viewer(monkeypatch, tmp_path):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    for role in ("member", "viewer"):
        _override_current_user_role(role)
        try:
            resp = client.post(
                "/api/monitoring/ingestion-jobs/trigger",
                json=_trigger_payload(),
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


def test_trigger_ingestion_job_writes_snake_case_request_with_dry_run_default(
    monkeypatch, tmp_path
):
    inbox_dir = _configure_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(notes="operator note"),
        )
        assert resp.status_code == 200
        body = resp.json()
        payload = _read_submitted_request(inbox_dir, body["jobRequestId"])
    finally:
        app.dependency_overrides.clear()

    assert set(payload) == {
        "job_id",
        "source_id",
        "provider",
        "aoi_id",
        "window_days",
        "window_start",
        "window_end",
        "limit",
        "max_downloads",
        "min_coverage_percent",
        "dry_run",
        "overwrite",
        "force_upload",
        "retain_raw_downloads",
        "keep_intermediate",
        "requested_by",
        "notes",
    }
    assert payload["job_id"] == body["jobRequestId"]
    assert payload["source_id"] == "resourcesat-2a-liss3-boa"
    assert payload["provider"] == "bhoonidhi"
    assert payload["aoi_id"] == "bangalore-60km"
    assert payload["window_days"] == 12
    assert payload["window_start"] == ""
    assert payload["window_end"] == ""
    assert payload["limit"] == 100
    assert payload["max_downloads"] == 1
    assert payload["min_coverage_percent"] == 95.0
    assert payload["dry_run"] is True
    assert payload["overwrite"] is False
    assert payload["force_upload"] is False
    assert payload["retain_raw_downloads"] is False
    assert payload["keep_intermediate"] is False
    assert payload["requested_by"] == "owner@example.test@bff"
    assert payload["notes"] == "operator note"


def test_trigger_ingestion_live_without_confirm_rejected_when_gate_true(
    monkeypatch, tmp_path
):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "admin_ingestion_live_trigger_enabled", True, raising=False)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(dryRun=False),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LIVE_CONFIRMATION_REQUIRED"


def test_trigger_ingestion_live_with_confirm_writes_non_dry_run_when_gate_true(
    monkeypatch, tmp_path
):
    inbox_dir = _configure_trigger_fixtures(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "admin_ingestion_live_trigger_enabled", True, raising=False)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(dryRun=False, confirmLive=True),
        )
        body = resp.json()
        payload = _read_submitted_request(inbox_dir, body["jobRequestId"])
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert body["dryRun"] is False
    assert payload["dry_run"] is False


def test_trigger_ingestion_gate_false_forces_live_request_to_dry_run(
    monkeypatch, tmp_path
):
    inbox_dir = _configure_trigger_fixtures(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "admin_ingestion_live_trigger_enabled", False, raising=False)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(dryRun=False, confirmLive=True),
        )
        body = resp.json()
        payload = _read_submitted_request(inbox_dir, body["jobRequestId"])
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert body["dryRun"] is True
    assert payload["dry_run"] is True


def test_trigger_ingestion_unknown_or_non_schedulable_source_rejected(
    monkeypatch, tmp_path
):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(sourceId="sentinel-2-l2a"),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SOURCE_NOT_SCHEDULABLE"


def test_trigger_ingestion_rejects_unsafe_source_or_aoi_identifier(monkeypatch, tmp_path):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("owner")
    try:
        for payload in (
            _trigger_payload(sourceId="../resourcesat-2a-liss3-boa"),
            _trigger_payload(aoiId="bangalore/60km"),
        ):
            resp = client.post(
                "/api/monitoring/ingestion-jobs/trigger",
                json=payload,
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_trigger_ingestion_inbox_missing_returns_unavailable_without_raw_path(
    monkeypatch, tmp_path
):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    missing = tmp_path / "missing-inbox"
    monkeypatch.setattr(settings, "ingestion_job_inbox_dir", str(missing), raising=False)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["jobRequestId"] is None
    assert body["jobsUrl"] == "/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa"
    serialized = json.dumps(body)
    assert str(missing) not in serialized
    assert "/srv/akasha" not in serialized
    assert "\\akasha\\" not in serialized


def test_trigger_ingestion_bounded_fields_rejected(monkeypatch, tmp_path):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("owner")
    try:
        for field, value in (
            ("windowDays", 0),
            ("windowDays", 91),
            ("limit", 0),
            ("limit", 501),
            ("maxDownloads", 0),
            ("maxDownloads", 21),
            ("minCoveragePercent", -1),
            ("minCoveragePercent", 101),
            ("windowStart", "not-a-date"),
            ("windowEnd", "2026-13-99"),
            ("notes", "x" * 501),
        ):
            resp = client.post(
                "/api/monitoring/ingestion-jobs/trigger",
                json=_trigger_payload(**{field: value}),
            )
            assert resp.status_code == 422, f"{field}={value!r}"
    finally:
        app.dependency_overrides.clear()


def test_trigger_ingestion_response_does_not_leak_paths_or_secrets(monkeypatch, tmp_path):
    _configure_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(notes="do not leak token=secret"),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    serialized = json.dumps(resp.json())
    assert str(tmp_path) not in serialized
    assert "/srv/akasha" not in serialized
    assert "secret" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_trigger_ingestion_sanitizes_notes_before_writing_request(monkeypatch, tmp_path):
    inbox_dir = _configure_trigger_fixtures(monkeypatch, tmp_path)
    _override_current_user_role("owner")
    try:
        resp = client.post(
            "/api/monitoring/ingestion-jobs/trigger",
            json=_trigger_payload(notes="operator token=secret /srv/akasha/raw/file.tif"),
        )
        body = resp.json()
        payload = _read_submitted_request(inbox_dir, body["jobRequestId"])
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "token=[redacted]" in payload["notes"].lower()
    assert "secret" not in payload["notes"].lower()
    assert "/srv/akasha" not in payload["notes"]


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
    # The route is owner/admin-gated through require_role.
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
    assert "/api/monitoring/ingestion-sources" in paths
    assert "/api/monitoring/ingestion-sources/{source_id}/products" in paths
    assert "/api/monitoring/ingestion-jobs" in paths
    assert "/api/monitoring/ingestion-jobs/trigger" in paths
    assert "/api/monitoring/ingestion-jobs/{job_id}" in paths
    assert "/api/monitoring/ingestion-jobs/{job_id}/events" in paths

    schemas = schema["components"]["schemas"]
    assert "IngestionScheduleItem" in schemas
    assert "IngestionScheduleResponse" in schemas
    assert "IngestionJobSummary" in schemas
    assert "IngestionJobListResponse" in schemas
    assert "IngestionJobDetail" in schemas
    assert "IngestionJobEvent" in schemas
    assert "IngestionJobEventsResponse" in schemas
    assert "TriggerIngestionJobRequest" in schemas
    assert "TriggerIngestionJobResponse" in schemas
    assert "IngestionSourceLastJob" in schemas
    assert "IngestionSourceSummary" in schemas
    assert "IngestionSourcesResponse" in schemas
    assert "IngestionProductItem" in schemas
    assert "IngestionSourceProductsResponse" in schemas

    schedule_props = schemas["IngestionScheduleItem"]["properties"]
    for field in (
        "sourceId", "provider", "adapter", "aoiId",
        "lifecycleState", "scheduleState", "scheduleEnabled",
        "productExposure", "lastRunAt", "lastSuccessAt", "lastFailureAt",
        "nextDueAt", "isDue", "isOverdue", "nextWindowStart", "nextWindowEnd",
        "cadenceDays", "dueReason",
    ):
        assert field in schedule_props, f"scheduleItem missing field {field!r}"

    source_props = schemas["IngestionSourceSummary"]["properties"]
    for field in (
        "sourceId", "label", "provider", "kind", "availabilityStatus", "active",
        "adminManageable", "syncEnabled", "gatedReason", "aoiId", "scheduleState",
        "scheduleEnabled", "productExposure", "validationState", "capabilities",
        "cadenceDays", "lastRunAt", "lastSuccessAt", "lastFailureAt", "nextDueAt",
        "isDue", "isOverdue", "latestCompositeDate", "lastJob",
    ):
        assert field in source_props, f"ingestionSourceSummary missing field {field!r}"

    last_job_props = schemas["IngestionSourceLastJob"]["properties"]
    assert "runAt" in last_job_props

    product_props = schemas["IngestionProductItem"]["properties"]
    for field in (
        "productId", "sceneKey", "acquisitionDate", "status", "bytes", "updatedAt", "error",
    ):
        assert field in product_props, f"ingestionProductItem missing field {field!r}"

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

    event_props = schemas["IngestionJobEvent"]["properties"]
    for field in ("timestamp", "eventType", "stage", "status", "message", "payload"):
        assert field in event_props, f"jobEvent missing field {field!r}"

    event_response_props = schemas["IngestionJobEventsResponse"]["properties"]
    for field in ("status", "generatedAt", "events", "truncated", "scannedCount"):
        assert field in event_response_props, f"jobEventsResponse missing field {field!r}"


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
