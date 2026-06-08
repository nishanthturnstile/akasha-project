-- Akasha Phase 12 — auth, teams, API key metadata, and ownership columns.

CREATE TABLE IF NOT EXISTS akasha.users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL UNIQUE,
    password_hash text,
    display_name  text,
    status        text NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_status_chk CHECK (status IN ('active', 'disabled'))
)
--;;
CREATE TABLE IF NOT EXISTS akasha.teams (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    created_by  uuid REFERENCES akasha.users(id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT teams_name_not_blank CHECK (length(btrim(name)) > 0)
)
--;;
CREATE TABLE IF NOT EXISTS akasha.memberships (
    team_id    uuid NOT NULL REFERENCES akasha.teams(id) ON DELETE CASCADE,
    user_id    uuid NOT NULL REFERENCES akasha.users(id) ON DELETE CASCADE,
    role       text NOT NULL DEFAULT 'owner',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id),
    CONSTRAINT memberships_role_chk CHECK (role IN ('owner', 'admin', 'member', 'viewer'))
)
--;;
CREATE TABLE IF NOT EXISTS akasha.sessions (
    token_hash text PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES akasha.users(id) ON DELETE CASCADE,
    team_id    uuid REFERENCES akasha.teams(id) ON DELETE SET NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
)
--;;
CREATE TABLE IF NOT EXISTS akasha.api_keys (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id      uuid NOT NULL REFERENCES akasha.teams(id) ON DELETE CASCADE,
    user_id      uuid REFERENCES akasha.users(id) ON DELETE SET NULL,
    name         text NOT NULL,
    key_hash     text NOT NULL,
    prefix       text NOT NULL,
    last4        text NOT NULL,
    last_used_at timestamptz,
    revoked_at   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
)
--;;
INSERT INTO akasha.users (id, email, display_name)
SELECT
    '00000000-0000-4000-8000-000000000001'::uuid,
    'dev@akasha.local',
    'Akasha Dev User'
WHERE NOT EXISTS (SELECT 1 FROM akasha.users WHERE email = 'dev@akasha.local')
  AND NOT EXISTS (
      SELECT 1 FROM akasha.users WHERE id = '00000000-0000-4000-8000-000000000001'::uuid
  )
--;;
INSERT INTO akasha.teams (id, name, created_by)
SELECT '00000000-0000-4000-8000-000000000010'::uuid, 'Akasha Dev Team', u.id
FROM akasha.users u
WHERE u.email = 'dev@akasha.local'
  AND NOT EXISTS (SELECT 1 FROM akasha.teams WHERE name = 'Akasha Dev Team')
  AND NOT EXISTS (
      SELECT 1 FROM akasha.teams WHERE id = '00000000-0000-4000-8000-000000000010'::uuid
  )
--;;
INSERT INTO akasha.memberships (team_id, user_id, role)
SELECT t.id, u.id, 'owner'
FROM (
    SELECT id FROM akasha.teams
    WHERE name = 'Akasha Dev Team'
    ORDER BY created_at, id
    LIMIT 1
) t
CROSS JOIN akasha.users u
WHERE u.email = 'dev@akasha.local'
ON CONFLICT DO NOTHING
--;;
ALTER TABLE akasha.plots
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
ALTER TABLE akasha.field_activities
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
ALTER TABLE akasha.scout_tasks
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
ALTER TABLE akasha.uploaded_datasets
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
ALTER TABLE akasha.field_groups
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
ALTER TABLE akasha.report_templates
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
ALTER TABLE akasha.attachments
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES akasha.users(id),
    ADD COLUMN IF NOT EXISTS team_id uuid REFERENCES akasha.teams(id)
--;;
UPDATE akasha.plots SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
UPDATE akasha.field_activities SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
UPDATE akasha.scout_tasks SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
UPDATE akasha.uploaded_datasets SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
UPDATE akasha.field_groups SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
UPDATE akasha.report_templates SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
UPDATE akasha.attachments SET team_id = (SELECT id FROM akasha.teams WHERE name = 'Akasha Dev Team' LIMIT 1)
WHERE team_id IS NULL
--;;
CREATE INDEX IF NOT EXISTS plots_team_idx ON akasha.plots (team_id)
--;;
CREATE INDEX IF NOT EXISTS field_activities_team_idx ON akasha.field_activities (team_id)
--;;
CREATE INDEX IF NOT EXISTS scout_tasks_team_idx ON akasha.scout_tasks (team_id)
--;;
CREATE INDEX IF NOT EXISTS uploaded_datasets_team_idx ON akasha.uploaded_datasets (team_id)
--;;
CREATE INDEX IF NOT EXISTS field_groups_team_idx ON akasha.field_groups (team_id)
--;;
CREATE INDEX IF NOT EXISTS report_templates_team_idx ON akasha.report_templates (team_id)
--;;
CREATE INDEX IF NOT EXISTS attachments_team_idx ON akasha.attachments (team_id)
--;;
DROP TRIGGER IF EXISTS users_set_updated_at ON akasha.users
--;;
CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON akasha.users
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
DROP TRIGGER IF EXISTS teams_set_updated_at ON akasha.teams
--;;
CREATE TRIGGER teams_set_updated_at BEFORE UPDATE ON akasha.teams
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
