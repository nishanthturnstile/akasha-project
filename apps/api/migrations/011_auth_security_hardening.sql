-- Akasha auth security hardening: deterministic dev principal IDs and remember-me sessions.

DO $$
DECLARE
    fixed_user_id CONSTANT uuid := '00000000-0000-4000-8000-000000000001'::uuid;
    fixed_team_id CONSTANT uuid := '00000000-0000-4000-8000-000000000010'::uuid;
    legacy_user_id uuid;
    legacy_team_id uuid;
BEGIN
    SELECT id INTO legacy_user_id
    FROM akasha.users
    WHERE email = 'dev@akasha.local'
      AND id <> fixed_user_id
    ORDER BY created_at, id
    LIMIT 1;

    IF legacy_user_id IS NOT NULL THEN
        UPDATE akasha.users
        SET email = 'dev+legacy-' || replace(legacy_user_id::text, '-', '') || '@akasha.local',
            username = 'dev_legacy_' || substr(replace(legacy_user_id::text, '-', ''), 1, 12)
        WHERE id = legacy_user_id;
    END IF;

    INSERT INTO akasha.users (id, email, username, display_name, status)
    VALUES (fixed_user_id, 'dev@akasha.local', 'dev', 'Akasha Dev User', 'active')
    ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        username = EXCLUDED.username,
        display_name = EXCLUDED.display_name,
        status = EXCLUDED.status;

    IF legacy_user_id IS NOT NULL THEN
        UPDATE akasha.teams SET created_by = fixed_user_id WHERE created_by = legacy_user_id;
        UPDATE akasha.sessions SET user_id = fixed_user_id WHERE user_id = legacy_user_id;
        UPDATE akasha.api_keys SET user_id = fixed_user_id WHERE user_id = legacy_user_id;
        UPDATE akasha.plots SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;
        UPDATE akasha.field_activities SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;
        UPDATE akasha.scout_tasks SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;
        UPDATE akasha.uploaded_datasets SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;
        UPDATE akasha.field_groups SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;
        UPDATE akasha.report_templates SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;
        UPDATE akasha.attachments SET owner_id = fixed_user_id WHERE owner_id = legacy_user_id;

        INSERT INTO akasha.memberships (team_id, user_id, role)
        SELECT team_id, fixed_user_id, role
        FROM akasha.memberships
        WHERE user_id = legacy_user_id
        ON CONFLICT DO NOTHING;
        DELETE FROM akasha.memberships WHERE user_id = legacy_user_id;
        DELETE FROM akasha.users WHERE id = legacy_user_id;
    END IF;

    SELECT id INTO legacy_team_id
    FROM akasha.teams
    WHERE name = 'Akasha Dev Team'
      AND id <> fixed_team_id
    ORDER BY created_at, id
    LIMIT 1;

    IF legacy_team_id IS NOT NULL THEN
        UPDATE akasha.teams
        SET name = 'Akasha Dev Team Legacy ' || substr(replace(legacy_team_id::text, '-', ''), 1, 12)
        WHERE id = legacy_team_id;
    END IF;

    INSERT INTO akasha.teams AS existing_team (id, name, created_by)
    VALUES (fixed_team_id, 'Akasha Dev Team', fixed_user_id)
    ON CONFLICT (id) DO UPDATE
    SET name = EXCLUDED.name,
        created_by = COALESCE(existing_team.created_by, EXCLUDED.created_by);

    IF legacy_team_id IS NOT NULL THEN
        UPDATE akasha.sessions SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.api_keys SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.notifications SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.plots SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.field_activities SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.scout_tasks SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.uploaded_datasets SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.field_groups SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.report_templates SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.attachments SET team_id = fixed_team_id WHERE team_id = legacy_team_id;
        UPDATE akasha.field_group_members SET team_id = fixed_team_id WHERE team_id = legacy_team_id;

        INSERT INTO akasha.memberships (team_id, user_id, role)
        SELECT fixed_team_id, user_id, role
        FROM akasha.memberships
        WHERE team_id = legacy_team_id
        ON CONFLICT DO NOTHING;
        DELETE FROM akasha.memberships WHERE team_id = legacy_team_id;
        DELETE FROM akasha.teams WHERE id = legacy_team_id;
    END IF;

    INSERT INTO akasha.memberships (team_id, user_id, role)
    VALUES (fixed_team_id, fixed_user_id, 'owner')
    ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role;
END $$;
--;;
ALTER TABLE akasha.sessions
    ADD COLUMN IF NOT EXISTS remember_me boolean NOT NULL DEFAULT false
