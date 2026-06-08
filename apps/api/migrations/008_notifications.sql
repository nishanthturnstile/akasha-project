-- Akasha Phase 12 — notifications.

CREATE TABLE IF NOT EXISTS akasha.notifications (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id       uuid REFERENCES akasha.teams(id) ON DELETE CASCADE,
    user_id       uuid REFERENCES akasha.users(id) ON DELETE SET NULL,
    type          text NOT NULL,
    title         text NOT NULL,
    body          text,
    resource_type text,
    resource_id   text,
    read_at       timestamptz,
    metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT notifications_type_chk CHECK (
        type IN ('field_change', 'risk_alert', 'task_assignment', 'report_available')
    ),
    CONSTRAINT notifications_metadata_object_chk CHECK (jsonb_typeof(metadata) = 'object')
)
--;;
CREATE INDEX IF NOT EXISTS notifications_team_read_idx
    ON akasha.notifications (team_id, read_at, created_at DESC)
--;;
DROP TRIGGER IF EXISTS notifications_set_updated_at ON akasha.notifications
--;;
CREATE TRIGGER notifications_set_updated_at BEFORE UPDATE ON akasha.notifications
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
