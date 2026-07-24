"""Canonical field discovery relationships and indexes.

Revision ID: 20260724_0007
Revises: 20260719_0004
Create Date: 2026-07-24 00:00:00.000000+00:00
"""

from __future__ import annotations

import re
import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "20260724_0007"
down_revision = "20260719_0004"
branch_labels = None
depends_on = None

SCHEMA = "akasha"
_DIGIT_RUN = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _WHITESPACE.sub(" ", without_marks.casefold()).strip()


def _natural_key(value: str) -> str:
    def encode_digits(match: re.Match[str]) -> str:
        digits = match.group(0).lstrip("0") or "0"
        return f"\x01{len(digits):08d}:{digits}\x01"

    return _DIGIT_RUN.sub(encode_digits, _normalize(value))


def _assert_team_backfill_complete(table: str) -> None:
    remaining = op.get_bind().execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.{table} WHERE team_id IS NULL")
    ).scalar_one()
    if remaining:
        raise RuntimeError(
            f"Cannot assign {remaining} {table} row(s) to one unambiguous team. "
            "Resolve team membership before rerunning the migration."
        )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # The baseline migration intentionally calls current Base.metadata.create_all().
    # IF NOT EXISTS keeps both fresh databases and upgraded live databases valid.
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.fields
            ADD COLUMN IF NOT EXISTS team_id uuid,
            ADD COLUMN IF NOT EXISTS name_search_key text,
            ADD COLUMN IF NOT EXISTS name_sort_key text,
            ADD COLUMN IF NOT EXISTS district text,
            ADD COLUMN IF NOT EXISTS country text;
        ALTER TABLE {SCHEMA}.seasons
            ADD COLUMN IF NOT EXISTS team_id uuid;
        ALTER TABLE {SCHEMA}.scout_tasks
            ADD COLUMN IF NOT EXISTS field_id uuid,
            ADD COLUMN IF NOT EXISTS field_name_snapshot text;
        """
    )
    for constraint_sql in (
        f"""
        ALTER TABLE {SCHEMA}.fields
        ADD CONSTRAINT fields_team_id_fkey FOREIGN KEY (team_id)
        REFERENCES {SCHEMA}.teams(id) ON DELETE CASCADE
        """,
        f"""
        ALTER TABLE {SCHEMA}.seasons
        ADD CONSTRAINT seasons_team_id_fkey FOREIGN KEY (team_id)
        REFERENCES {SCHEMA}.teams(id) ON DELETE CASCADE
        """,
        f"""
        ALTER TABLE {SCHEMA}.scout_tasks
        ADD CONSTRAINT scout_tasks_field_id_fkey FOREIGN KEY (field_id)
        REFERENCES {SCHEMA}.fields(id) ON DELETE SET NULL
        """,
    ):
        constraint_name = constraint_sql.split("ADD CONSTRAINT ", 1)[1].split()[0]
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'
                ) THEN
                    {constraint_sql};
                END IF;
            END $$;
            """
        )

    # Team resolution is intentionally fail-closed. A sole membership wins; otherwise
    # exactly one team created by the field/season owner wins.
    for table, primary_key in (("fields", "id"), ("seasons", "season_id")):
        op.execute(
            f"""
            WITH candidates AS (
                SELECT source.{primary_key} AS source_id,
                       COALESCE(
                           CASE
                               WHEN count(m.team_id) = 1
                               THEN (array_agg(m.team_id) FILTER (WHERE m.team_id IS NOT NULL))[1]
                           END,
                           CASE
                               WHEN count(m.team_id) FILTER (WHERE t.created_by = source.user_id) = 1
                               THEN (
                                   array_agg(m.team_id)
                                   FILTER (WHERE t.created_by = source.user_id)
                               )[1]
                           END
                       ) AS resolved_team_id
                FROM {SCHEMA}.{table} source
                LEFT JOIN {SCHEMA}.memberships m ON m.user_id = source.user_id
                LEFT JOIN {SCHEMA}.teams t ON t.id = m.team_id
                GROUP BY source.{primary_key}
            )
            UPDATE {SCHEMA}.{table} source
            SET team_id = candidates.resolved_team_id
            FROM candidates
            WHERE source.{primary_key} = candidates.source_id
            """
        )
        _assert_team_backfill_complete(table)

    bind = op.get_bind()
    field_names = bind.execute(sa.text(f"SELECT id, name FROM {SCHEMA}.fields")).all()
    for field_id, name in field_names:
        bind.execute(
            sa.text(
                f"""
                UPDATE {SCHEMA}.fields
                SET name_search_key = :search_key, name_sort_key = :sort_key
                WHERE id = :field_id
                """
            ),
            {
                "field_id": field_id,
                "search_key": _normalize(name),
                "sort_key": _natural_key(name),
            },
        )

    op.execute(
        f"""
        UPDATE {SCHEMA}.fields
        SET area_ha = ST_Area(geometry::geography) / 10000.0
        """
    )
    invalid_area_count = bind.execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.fields WHERE area_ha <= 0")
    ).scalar_one()
    if invalid_area_count:
        raise RuntimeError(
            f"Cannot derive a positive geodesic area for {invalid_area_count} field row(s)."
        )

    # Migrate only provably identical legacy links. Ambiguous legacy rows remain
    # readable through plot_id and field_name_snapshot.
    op.execute(
        f"""
        UPDATE {SCHEMA}.scout_tasks task
        SET field_id = field.id,
            field_name_snapshot = field.name
        FROM {SCHEMA}.fields field
        WHERE task.field_id IS NULL
          AND task.plot_id = field.id
          AND task.team_id = field.team_id
        """
    )
    op.execute(
        f"""
        WITH unique_matches AS (
            SELECT task.id AS task_id,
                   (array_agg(field.id))[1] AS field_id,
                   count(*) AS match_count
            FROM {SCHEMA}.scout_tasks task
            JOIN {SCHEMA}.plots plot ON plot.id = task.plot_id
            JOIN {SCHEMA}.fields field
              ON field.team_id = task.team_id
             AND lower(unaccent(regexp_replace(btrim(field.name), '\\s+', ' ', 'g')))
                 = lower(unaccent(regexp_replace(btrim(plot.name), '\\s+', ' ', 'g')))
             AND ST_Equals(field.geometry, plot.geometry)
            WHERE task.field_id IS NULL
            GROUP BY task.id
        )
        UPDATE {SCHEMA}.scout_tasks task
        SET field_id = matches.field_id,
            field_name_snapshot = field.name
        FROM unique_matches matches
        JOIN {SCHEMA}.fields field ON field.id = matches.field_id
        WHERE task.id = matches.task_id
          AND matches.match_count = 1
        """
    )
    op.execute(
        f"""
        WITH shared_matches AS (
            SELECT plot.id AS plot_id, field.id AS field_id
            FROM {SCHEMA}.plots plot
            JOIN {SCHEMA}.fields field
              ON field.id = plot.id
             AND field.team_id = plot.team_id
        ),
        named_candidates AS (
            SELECT plot.id AS plot_id,
                   field.id AS field_id,
                   count(*) OVER (PARTITION BY plot.id) AS match_count
            FROM {SCHEMA}.plots plot
            JOIN {SCHEMA}.fields field
              ON field.team_id = plot.team_id
             AND lower(unaccent(regexp_replace(btrim(field.name), '\\s+', ' ', 'g')))
                 = lower(unaccent(regexp_replace(btrim(plot.name), '\\s+', ' ', 'g')))
             AND ST_Equals(field.geometry, plot.geometry)
            WHERE NOT EXISTS (
                SELECT 1 FROM shared_matches shared WHERE shared.plot_id = plot.id
            )
        ),
        mapped AS (
            SELECT plot_id, field_id FROM shared_matches
            UNION ALL
            SELECT plot_id, field_id FROM named_candidates WHERE match_count = 1
        ),
        unambiguous_groups AS (
            SELECT mapped.field_id,
                   (array_agg(DISTINCT member.group_id))[1] AS group_id
            FROM mapped
            JOIN {SCHEMA}.field_group_members member ON member.plot_id = mapped.plot_id
            JOIN {SCHEMA}.field_groups group_row
              ON group_row.id = member.group_id
            JOIN {SCHEMA}.fields field ON field.id = mapped.field_id
            WHERE group_row.team_id = field.team_id
            GROUP BY mapped.field_id
            HAVING count(DISTINCT member.group_id) = 1
        )
        UPDATE {SCHEMA}.fields field
        SET group_id = unambiguous_groups.group_id
        FROM unambiguous_groups
        WHERE field.id = unambiguous_groups.field_id
          AND field.group_id IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.scout_tasks task
        SET field_name_snapshot = plot.name
        FROM {SCHEMA}.plots plot
        WHERE task.plot_id = plot.id
          AND task.field_name_snapshot IS NULL
        """
    )

    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.fields
            ALTER COLUMN team_id SET NOT NULL,
            ALTER COLUMN name_search_key SET NOT NULL,
            ALTER COLUMN name_sort_key SET NOT NULL;
        ALTER TABLE {SCHEMA}.seasons ALTER COLUMN team_id SET NOT NULL;

        CREATE INDEX IF NOT EXISTS fields_team_created_idx
            ON {SCHEMA}.fields (team_id, created_at DESC, id);
        CREATE INDEX IF NOT EXISTS fields_team_name_sort_idx
            ON {SCHEMA}.fields (team_id, name_sort_key, id);
        CREATE INDEX IF NOT EXISTS fields_team_area_idx
            ON {SCHEMA}.fields (team_id, area_ha, id);
        CREATE INDEX IF NOT EXISTS fields_team_group_idx
            ON {SCHEMA}.fields (team_id, group_id);
        CREATE INDEX IF NOT EXISTS fields_name_search_trgm_idx
            ON {SCHEMA}.fields USING gin (name_search_key gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS seasons_team_idx ON {SCHEMA}.seasons (team_id);
        CREATE INDEX IF NOT EXISTS scout_tasks_team_field_idx
            ON {SCHEMA}.scout_tasks (team_id, field_id);
        CREATE INDEX IF NOT EXISTS scout_tasks_team_status_created_idx
            ON {SCHEMA}.scout_tasks (team_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS vegetation_cycles_season_crop_field_idx
            ON {SCHEMA}.vegetation_cycles (season_id, crop_id, field_id);
        """
    )


def downgrade() -> None:
    for index, table in (
        ("vegetation_cycles_season_crop_field_idx", "vegetation_cycles"),
        ("scout_tasks_team_status_created_idx", "scout_tasks"),
        ("scout_tasks_team_field_idx", "scout_tasks"),
        ("seasons_team_idx", "seasons"),
        ("fields_name_search_trgm_idx", "fields"),
        ("fields_team_group_idx", "fields"),
        ("fields_team_area_idx", "fields"),
        ("fields_team_name_sort_idx", "fields"),
        ("fields_team_created_idx", "fields"),
    ):
        op.drop_index(index, table_name=table, schema=SCHEMA)

    op.drop_constraint("scout_tasks_field_id_fkey", "scout_tasks", schema=SCHEMA, type_="foreignkey")
    op.drop_column("scout_tasks", "field_name_snapshot", schema=SCHEMA)
    op.drop_column("scout_tasks", "field_id", schema=SCHEMA)
    op.drop_constraint("seasons_team_id_fkey", "seasons", schema=SCHEMA, type_="foreignkey")
    op.drop_column("seasons", "team_id", schema=SCHEMA)
    op.drop_constraint("fields_team_id_fkey", "fields", schema=SCHEMA, type_="foreignkey")
    op.drop_column("fields", "country", schema=SCHEMA)
    op.drop_column("fields", "district", schema=SCHEMA)
    op.drop_column("fields", "name_sort_key", schema=SCHEMA)
    op.drop_column("fields", "name_search_key", schema=SCHEMA)
    op.drop_column("fields", "team_id", schema=SCHEMA)
