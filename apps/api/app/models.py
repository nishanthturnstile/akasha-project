"""SQLAlchemy ORM models for API-owned Akasha tables.

The API owns only the `akasha` app schema. pgSTAC/catalog schemas remain owned
by the ingestion service and are intentionally not modeled here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AKASHA_SCHEMA = "akasha"


class Base(DeclarativeBase):
    pass


class UuidPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class OwnerTeamMixin:
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="SET NULL"),
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.teams.id", ondelete="SET NULL"),
    )


class Plot(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "plots"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="plots_name_not_blank"),
        CheckConstraint(
            "GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON') AND ST_IsValid(geometry)",
            name="plots_geometry_type_chk",
        ),
        CheckConstraint(
            "status IS NULL OR status IN ('planned', 'active', 'inactive', 'archived')",
            name="plots_status_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        nullable=False,
    )
    area_ha: Mapped[float | None] = mapped_column(Float)
    group_name: Mapped[str | None] = mapped_column(Text)
    crop_type: Mapped[str | None] = mapped_column(Text)
    variety: Mapped[str | None] = mapped_column(Text)
    season_label: Mapped[str | None] = mapped_column(Text)
    sowing_date: Mapped[date | None] = mapped_column(Date)
    planting_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(Text)


class IndexRequest(UuidPkMixin, Base):
    __tablename__ = "index_requests"
    __table_args__ = {"schema": AKASHA_SCHEMA}

    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    index_type: Mapped[str] = mapped_column(Text, nullable=False)
    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.plots.id", ondelete="SET NULL"),
    )
    geometry: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = {"schema": AKASHA_SCHEMA}

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Season(TimestampMixin, Base):
    __tablename__ = "seasons"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="seasons_name_not_blank"),
        {"schema": AKASHA_SCHEMA},
    )

    season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    can_delete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class User(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="users_email_key"),
        CheckConstraint("status IN ('active', 'disabled')", name="users_status_chk"),
        CheckConstraint(
            "username IS NULL OR length(btrim(username)) > 0",
            name="users_username_not_blank",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Team(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="teams_name_not_blank"),
        {"schema": AKASHA_SCHEMA},
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="SET NULL"),
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="memberships_role_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'owner'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class AuthSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": AKASHA_SCHEMA}

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.teams.id", ondelete="SET NULL"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent_hash: Mapped[str | None] = mapped_column(Text)
    remember_me: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ApiKey(UuidPkMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = {"schema": AKASHA_SCHEMA}

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="SET NULL"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    last4: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Notification(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('field_change', 'risk_alert', 'task_assignment', 'report_available')",
            name="notifications_type_chk",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="notifications_metadata_object_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.teams.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="SET NULL"),
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class ReportTemplate(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "report_templates"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="report_templates_name_not_blank"),
        CheckConstraint(
            "jsonb_typeof(columns) = 'array'",
            name="report_templates_columns_array_chk",
        ),
        CheckConstraint(
            "jsonb_typeof(filters) = 'object'",
            name="report_templates_filters_object_chk",
        ),
        CheckConstraint("jsonb_typeof(sort) = 'object'", name="report_templates_sort_object_chk"),
        {"schema": AKASHA_SCHEMA},
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    columns: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    sort: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class FieldGroup(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "field_groups"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="field_groups_name_not_blank"),
        {"schema": AKASHA_SCHEMA},
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(Text)


class FieldGroupMember(Base):
    __tablename__ = "field_group_members"
    __table_args__ = {"schema": AKASHA_SCHEMA}

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.field_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    plot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.plots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.teams.id", ondelete="CASCADE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Field(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "fields"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="fields_name_not_blank"),
        CheckConstraint(
            "GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON') AND ST_IsValid(geometry)",
            name="fields_geometry_type_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    area_ha: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        nullable=False,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.field_groups.id", ondelete="SET NULL"),
    )


class FieldSeason(UuidPkMixin, Base):
    __tablename__ = "field_seasons"
    __table_args__ = (
        UniqueConstraint("season_id", "field_id", name="field_seasons_unique_pair"),
        {"schema": AKASHA_SCHEMA},
    )

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.seasons.season_id", ondelete="CASCADE"),
        nullable=False,
    )


class Attachment(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "parent_type IS NULL OR parent_type IN ('activity', 'scout_task', 'dataset')",
            name="attachments_parent_type_chk",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="attachments_metadata_object_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    parent_type: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    internal_storage_key: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class FieldActivity(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "field_activities"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'in_progress', 'done', 'cancelled')",
            name="field_activities_status_chk",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="field_activities_metadata_object_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.plots.id", ondelete="SET NULL"),
    )
    activity_type: Mapped[str] = mapped_column(Text, nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    assignee: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'planned'"))
    input_product: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[Decimal | None] = mapped_column(Numeric)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class ScoutTask(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "scout_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('new', 'closed')", name="scout_tasks_status_chk"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="scout_tasks_priority_chk"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="scout_tasks_lng_chk",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="scout_tasks_lat_chk",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="scout_tasks_metadata_object_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AKASHA_SCHEMA}.plots.id", ondelete="SET NULL"),
    )
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'"))
    assignee: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'medium'"))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class UploadedDataset(UuidPkMixin, TimestampMixin, OwnerTeamMixin, Base):
    __tablename__ = "uploaded_datasets"
    __table_args__ = (
        CheckConstraint(
            "dataset_type IN ('geojson', 'shp_zip', 'iso_xml')",
            name="uploaded_datasets_type_chk",
        ),
        CheckConstraint(
            "upload_status IN ('uploaded', 'parsed', 'failed')",
            name="uploaded_datasets_status_chk",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="uploaded_datasets_metadata_object_chk",
        ),
        {"schema": AKASHA_SCHEMA},
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_type: Mapped[str] = mapped_column(Text, nullable=False)
    upload_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'uploaded'"),
    )
    original_filename: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    feature_count: Mapped[int | None] = mapped_column(Integer)
    validation_message: Mapped[str | None] = mapped_column(Text)
    internal_storage_key: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


Index("plots_geometry_gix", Plot.geometry, postgresql_using="gist")
Index("plots_created_at_idx", Plot.created_at.desc())
Index("plots_status_idx", Plot.status)
Index("plots_team_idx", Plot.team_id)
Index("index_requests_created_at_idx", IndexRequest.created_at.desc())
Index(
    "users_username_lower_uidx",
    func.lower(User.username),
    unique=True,
    postgresql_where=User.username.is_not(None),
)
Index("sessions_id_uidx", AuthSession.id, unique=True)
Index(
    "sessions_user_active_idx",
    AuthSession.user_id,
    AuthSession.expires_at,
    postgresql_where=AuthSession.revoked_at.is_(None),
)
Index(
    "sessions_team_active_idx",
    AuthSession.team_id,
    AuthSession.expires_at,
    postgresql_where=AuthSession.revoked_at.is_(None),
)
Index(
    "notifications_team_read_idx",
    Notification.team_id,
    Notification.read_at,
    Notification.created_at.desc(),
)
Index("report_templates_created_idx", ReportTemplate.created_at.desc())
Index("report_templates_team_idx", ReportTemplate.team_id)
Index("field_groups_team_idx", FieldGroup.team_id)
Index("field_group_members_team_idx", FieldGroupMember.team_id)
Index("attachments_parent_idx", Attachment.parent_type, Attachment.parent_id)
Index("attachments_team_idx", Attachment.team_id)
Index("field_activities_plot_date_idx", FieldActivity.plot_id, FieldActivity.activity_date.desc())
Index("field_activities_team_idx", FieldActivity.team_id)
Index("scout_tasks_status_idx", ScoutTask.status)
Index("scout_tasks_team_idx", ScoutTask.team_id)
Index("uploaded_datasets_created_idx", UploadedDataset.created_at.desc())
Index("uploaded_datasets_team_idx", UploadedDataset.team_id)
Index("fields_geometry_gix", Field.geometry, postgresql_using="gist")
Index("fields_user_idx", Field.user_id)
Index("field_seasons_field_idx", FieldSeason.field_id)
Index("field_seasons_season_idx", FieldSeason.season_id)
