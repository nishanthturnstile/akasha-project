"""Optional integration tests for the SQLAlchemy/Alembic app schema baseline.

These tests are intentionally skipped unless AKASHA_TEST_DATABASE_URL points to
a disposable PostgreSQL/PostGIS database. They drop the API-owned app schema and
Alembic version table before applying the fresh baseline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.repositories import account_repo, auth_repo, phase10_repo, plots_repo, reports_repo
from app.auth import DEV_TEAM_ID, DEV_USER_ID
from app.db import get_engine, reset_engine_for_tests, session_scope
from app.models import AKASHA_SCHEMA, Notification
from sqlalchemy import text

VALID_POLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [77.60, 12.95],
            [77.61, 12.95],
            [77.61, 12.96],
            [77.60, 12.96],
            [77.60, 12.95],
        ]
    ],
}


@pytest.fixture()
def disposable_db(monkeypatch):
    dsn = pytest.importorskip("os").environ.get("AKASHA_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("AKASHA_TEST_DATABASE_URL is not set")
    monkeypatch.setenv("DATABASE_URL", dsn)
    reset_engine_for_tests()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {AKASHA_SCHEMA} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


def test_alembic_baseline_creates_expected_schema(disposable_db):
    with get_engine().connect() as conn:
        tables = {}
        for name in (
            "plots",
            "users",
            "teams",
            "memberships",
            "sessions",
            "api_keys",
            "notifications",
            "report_templates",
            "field_activities",
            "scout_tasks",
            "field_groups",
            "field_group_members",
            "uploaded_datasets",
        ):
            tables[name] = conn.execute(
                text(f"SELECT to_regclass('akasha.{name}') IS NOT NULL")
            ).scalar_one()
        assert all(tables.values()), tables
        assert conn.execute(text("SELECT to_regclass('akasha.plots_geometry_gix')")).scalar_one()
        dev_user = conn.execute(
            text("SELECT username FROM akasha.users WHERE id = :id"),
            {"id": DEV_USER_ID},
        ).scalar_one()
        dev_team = conn.execute(
            text("SELECT name FROM akasha.teams WHERE id = :id"),
            {"id": DEV_TEAM_ID},
        ).scalar_one()
    assert dev_user == "dev"
    assert dev_team == "Akasha Dev Team"


def test_orm_repositories_round_trip(disposable_db):
    suffix = uuid.uuid4().hex[:8]

    plot = plots_repo.create_plot(
        f"North {suffix}",
        VALID_POLY,
        1.23,
        {"cropType": "rice", "status": "active"},
        owner_id=DEV_USER_ID,
        team_id=DEV_TEAM_ID,
    )
    assert plots_repo.get_plot(plot["id"], DEV_TEAM_ID)["cropType"] == "rice"
    assert plots_repo.update_plot(plot["id"], name=f"North updated {suffix}", team_id=DEV_TEAM_ID)

    template = reports_repo.create_report_template(
        name=f"Template {suffix}",
        columns=["fieldName"],
        filters={},
        sort={},
        owner_id=DEV_USER_ID,
        team_id=DEV_TEAM_ID,
    )
    assert reports_repo.get_report_template(template["id"], DEV_TEAM_ID)["columns"] == ["fieldName"]

    api_key = account_repo.create_api_key(
        team_id=DEV_TEAM_ID,
        user_id=DEV_USER_ID,
        name=f"Key {suffix}",
        key_hash=f"hash-{suffix}",
        prefix="akasha_test",
        last4=suffix[-4:],
    )
    assert any(row["id"] == api_key["id"] for row in account_repo.list_api_keys(DEV_TEAM_ID))
    assert account_repo.revoke_api_key(team_id=DEV_TEAM_ID, key_id=api_key["id"])

    with session_scope() as session:
        note = Notification(
            team_id=uuid.UUID(DEV_TEAM_ID),
            user_id=uuid.UUID(DEV_USER_ID),
            type="field_change",
            title=f"Notice {suffix}",
            metadata_json={},
        )
        session.add(note)
        session.flush()
        note_id = str(note.id)
    assert account_repo.unread_notification_count(DEV_TEAM_ID) == 1
    assert account_repo.mark_notification_read(team_id=DEV_TEAM_ID, notification_id=note_id)

    token_hash = f"token-{suffix}"
    auth_repo.create_session(
        token_hash=token_hash,
        user_id=DEV_USER_ID,
        team_id=DEV_TEAM_ID,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_agent_hash=None,
    )
    assert auth_repo.get_session_context(token_hash)["teamId"] == DEV_TEAM_ID
    assert auth_repo.rotate_session(
        token_hash,
        f"rotated-{suffix}",
        datetime.now(UTC) + timedelta(hours=1),
    )
    auth_repo.revoke_session(f"rotated-{suffix}")
    assert auth_repo.get_session_context(f"rotated-{suffix}") is None

    attachment = phase10_repo.create_attachment(
        filename=f"note-{suffix}.txt",
        content_type="text/plain",
        size_bytes=4,
        owner_id=DEV_USER_ID,
        team_id=DEV_TEAM_ID,
    )
    activity = phase10_repo.create_activity(
        {
            "plotId": plot["id"],
            "activityType": "spray",
            "activityDate": "2026-06-09",
            "ownerId": DEV_USER_ID,
            "teamId": DEV_TEAM_ID,
        },
        [attachment["id"]],
    )
    assert activity["attachments"][0]["id"] == attachment["id"]

    group = phase10_repo.create_field_group(
        {"name": f"Group {suffix}", "ownerId": DEV_USER_ID, "teamId": DEV_TEAM_ID}
    )
    assigned = phase10_repo.assign_group_fields(group["id"], [plot["id"], plot["id"]], DEV_TEAM_ID)
    assert assigned["plotIds"] == [plot["id"]]

    dataset = phase10_repo.create_dataset(
        {"name": f"Dataset {suffix}", "datasetType": "geojson", "teamId": DEV_TEAM_ID}
    )
    assert dataset["uploadStatus"] == "uploaded"
    assert plots_repo.delete_plot(plot["id"], DEV_TEAM_ID)
