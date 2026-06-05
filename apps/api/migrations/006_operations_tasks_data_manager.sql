-- Akasha Phase 10 — first-party operations, scouting, data manager, and field groups.

CREATE TABLE IF NOT EXISTS akasha.field_groups (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    description text,
    color       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT field_groups_name_not_blank CHECK (length(btrim(name)) > 0)
)
--;;
CREATE TABLE IF NOT EXISTS akasha.field_group_members (
    group_id uuid NOT NULL REFERENCES akasha.field_groups(id) ON DELETE CASCADE,
    plot_id  uuid NOT NULL REFERENCES akasha.plots(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, plot_id)
)
--;;
CREATE TABLE IF NOT EXISTS akasha.attachments (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_type          text,
    parent_id            uuid,
    filename             text NOT NULL,
    content_type         text,
    size_bytes           bigint,
    internal_storage_key text,
    metadata             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT attachments_parent_type_chk CHECK (
        parent_type IS NULL OR parent_type IN ('activity', 'scout_task', 'dataset')
    ),
    CONSTRAINT attachments_metadata_object_chk CHECK (jsonb_typeof(metadata) = 'object')
)
--;;
CREATE TABLE IF NOT EXISTS akasha.field_activities (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plot_id       uuid REFERENCES akasha.plots(id) ON DELETE SET NULL,
    activity_type text NOT NULL,
    activity_date date NOT NULL,
    assignee      text,
    status        text NOT NULL DEFAULT 'planned',
    input_product text,
    cost          numeric,
    notes         text,
    metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT field_activities_status_chk CHECK (
        status IN ('planned', 'in_progress', 'done', 'cancelled')
    ),
    CONSTRAINT field_activities_metadata_object_chk CHECK (jsonb_typeof(metadata) = 'object')
)
--;;
CREATE TABLE IF NOT EXISTS akasha.scout_tasks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plot_id     uuid REFERENCES akasha.plots(id) ON DELETE SET NULL,
    longitude   double precision,
    latitude    double precision,
    status      text NOT NULL DEFAULT 'new',
    assignee    text,
    priority    text NOT NULL DEFAULT 'medium',
    notes       text,
    metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT scout_tasks_status_chk CHECK (status IN ('new', 'closed')),
    CONSTRAINT scout_tasks_priority_chk CHECK (priority IN ('low', 'medium', 'high')),
    CONSTRAINT scout_tasks_lng_chk CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    CONSTRAINT scout_tasks_lat_chk CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CONSTRAINT scout_tasks_metadata_object_chk CHECK (jsonb_typeof(metadata) = 'object')
)
--;;
CREATE TABLE IF NOT EXISTS akasha.uploaded_datasets (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text NOT NULL,
    dataset_type         text NOT NULL,
    upload_status        text NOT NULL DEFAULT 'uploaded',
    original_filename    text,
    content_type         text,
    file_size_bytes      bigint,
    feature_count        integer,
    validation_message   text,
    internal_storage_key text,
    metadata             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uploaded_datasets_type_chk CHECK (
        dataset_type IN ('geojson', 'shp_zip', 'iso_xml')
    ),
    CONSTRAINT uploaded_datasets_status_chk CHECK (
        upload_status IN ('uploaded', 'parsed', 'failed')
    ),
    CONSTRAINT uploaded_datasets_metadata_object_chk CHECK (jsonb_typeof(metadata) = 'object')
)
--;;
CREATE INDEX IF NOT EXISTS field_activities_plot_date_idx
    ON akasha.field_activities (plot_id, activity_date DESC)
--;;
CREATE INDEX IF NOT EXISTS scout_tasks_status_idx ON akasha.scout_tasks (status)
--;;
CREATE INDEX IF NOT EXISTS attachments_parent_idx ON akasha.attachments (parent_type, parent_id)
--;;
CREATE INDEX IF NOT EXISTS uploaded_datasets_created_idx
    ON akasha.uploaded_datasets (created_at DESC)
--;;
DROP TRIGGER IF EXISTS field_groups_set_updated_at ON akasha.field_groups
--;;
CREATE TRIGGER field_groups_set_updated_at BEFORE UPDATE ON akasha.field_groups
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
DROP TRIGGER IF EXISTS attachments_set_updated_at ON akasha.attachments
--;;
CREATE TRIGGER attachments_set_updated_at BEFORE UPDATE ON akasha.attachments
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
DROP TRIGGER IF EXISTS field_activities_set_updated_at ON akasha.field_activities
--;;
CREATE TRIGGER field_activities_set_updated_at BEFORE UPDATE ON akasha.field_activities
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
DROP TRIGGER IF EXISTS scout_tasks_set_updated_at ON akasha.scout_tasks
--;;
CREATE TRIGGER scout_tasks_set_updated_at BEFORE UPDATE ON akasha.scout_tasks
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
DROP TRIGGER IF EXISTS uploaded_datasets_set_updated_at ON akasha.uploaded_datasets
--;;
CREATE TRIGGER uploaded_datasets_set_updated_at BEFORE UPDATE ON akasha.uploaded_datasets
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
