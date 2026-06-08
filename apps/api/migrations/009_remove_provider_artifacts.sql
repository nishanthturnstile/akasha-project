-- Remove cancelled integration artifacts from databases that applied those
-- migrations before the integration was removed.

DROP TABLE IF EXISTS akasha.zoning_maps
--;;
DROP INDEX IF EXISTS akasha.plots_external_provider_field_uidx
--;;
DROP INDEX IF EXISTS akasha.plots_provider_sync_status_idx
--;;
ALTER TABLE IF EXISTS akasha.plots DROP CONSTRAINT IF EXISTS plots_provider_sync_status_chk
--;;
ALTER TABLE IF EXISTS akasha.plots DROP CONSTRAINT IF EXISTS plots_provider_metadata_object_chk
--;;
ALTER TABLE IF EXISTS akasha.plots
    DROP COLUMN IF EXISTS external_provider,
    DROP COLUMN IF EXISTS external_field_id,
    DROP COLUMN IF EXISTS provider_sync_status,
    DROP COLUMN IF EXISTS provider_synced_at,
    DROP COLUMN IF EXISTS provider_metadata
--;;
ALTER TABLE IF EXISTS akasha.notifications DROP CONSTRAINT IF EXISTS notifications_type_chk
--;;
ALTER TABLE IF EXISTS akasha.notifications
    ADD CONSTRAINT notifications_type_chk
    CHECK (type IN ('field_change', 'risk_alert', 'task_assignment', 'report_available'))
