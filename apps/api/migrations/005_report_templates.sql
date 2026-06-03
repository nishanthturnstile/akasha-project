-- Akasha Phase 9 — report template persistence.
--
-- Single-tenant until Phase 12 ownership/team migrations add user scoping.

CREATE TABLE IF NOT EXISTS akasha.report_templates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    columns     jsonb NOT NULL DEFAULT '[]'::jsonb,
    filters     jsonb NOT NULL DEFAULT '{}'::jsonb,
    sort        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_templates_name_not_blank CHECK (length(btrim(name)) > 0),
    CONSTRAINT report_templates_columns_array_chk CHECK (jsonb_typeof(columns) = 'array'),
    CONSTRAINT report_templates_filters_object_chk CHECK (jsonb_typeof(filters) = 'object'),
    CONSTRAINT report_templates_sort_object_chk CHECK (jsonb_typeof(sort) = 'object')
)
--;;
CREATE INDEX IF NOT EXISTS report_templates_created_idx
    ON akasha.report_templates (created_at DESC)
--;;
DROP TRIGGER IF EXISTS report_templates_set_updated_at ON akasha.report_templates
--;;
CREATE TRIGGER report_templates_set_updated_at BEFORE UPDATE ON akasha.report_templates
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
