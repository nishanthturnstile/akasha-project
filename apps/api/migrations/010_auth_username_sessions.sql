-- Akasha auth hardening — username login, session rotation, and team scoping helpers.

ALTER TABLE akasha.users
    ADD COLUMN IF NOT EXISTS username text,
    ADD COLUMN IF NOT EXISTS last_login_at timestamptz,
    ADD COLUMN IF NOT EXISTS password_updated_at timestamptz,
    ADD COLUMN IF NOT EXISTS failed_login_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until timestamptz
--;;
UPDATE akasha.users
SET username = split_part(email, '@', 1)
WHERE username IS NULL
--;;
UPDATE akasha.users
SET username = 'dev'
WHERE email = 'dev@akasha.local'
--;;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uidx
    ON akasha.users (lower(username))
    WHERE username IS NOT NULL
--;;
ALTER TABLE akasha.users DROP CONSTRAINT IF EXISTS users_username_not_blank
--;;
ALTER TABLE akasha.users
    ADD CONSTRAINT users_username_not_blank
    CHECK (username IS NULL OR length(btrim(username)) > 0)
--;;
ALTER TABLE akasha.sessions
    ADD COLUMN IF NOT EXISTS id uuid DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS rotated_at timestamptz,
    ADD COLUMN IF NOT EXISTS revoked_at timestamptz,
    ADD COLUMN IF NOT EXISTS user_agent_hash text
--;;
CREATE UNIQUE INDEX IF NOT EXISTS sessions_id_uidx ON akasha.sessions (id)
--;;
CREATE INDEX IF NOT EXISTS sessions_user_active_idx
    ON akasha.sessions (user_id, expires_at)
    WHERE revoked_at IS NULL
--;;
CREATE INDEX IF NOT EXISTS sessions_team_active_idx
    ON akasha.sessions (team_id, expires_at)
    WHERE revoked_at IS NULL
--;;
ALTER TABLE akasha.field_group_members
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id) ON DELETE CASCADE
--;;
UPDATE akasha.field_group_members fgm
SET team_id = fg.team_id
FROM akasha.field_groups fg
WHERE fgm.group_id = fg.id
  AND fgm.team_id IS NULL
--;;
CREATE INDEX IF NOT EXISTS field_group_members_team_idx
    ON akasha.field_group_members (team_id)
