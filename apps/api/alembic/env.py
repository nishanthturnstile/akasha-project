from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.db import get_database_url
from app.models import AKASHA_SCHEMA, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:
    """Restrict autogenerate to the API-owned ``akasha`` schema.

    The database also hosts PostGIS-managed objects (e.g. ``public.spatial_ref_sys``)
    and the catalog/pgSTAC schema, none of which are owned by the API ORM. Limiting
    reflection to the ``akasha`` schema keeps ``alembic check`` from proposing to drop
    those external tables.
    """
    if type_ == "schema":
        return name == AKASHA_SCHEMA
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    # Pin the session search_path to ``public`` so Alembic's ``default_schema_name``
    # is deterministic. Otherwise, when the database role name matches the API schema
    # (e.g. role ``akasha`` + schema ``akasha`` in CI), ``$user`` resolves to the
    # ``akasha`` schema and Alembic treats those tables as the unnamed default schema.
    # Combined with ``include_name`` that excludes the default schema, autogenerate
    # would then see an empty database and report every ORM table as newly added.
    connectable = create_engine(
        get_database_url(),
        pool_pre_ping=True,
        future=True,
        connect_args={"options": "-csearch_path=public"},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
