-- Render-backed clones store Render service IDs separately from legacy Docker IDs.
ALTER TABLE clone_instances
    ADD COLUMN IF NOT EXISTS render_service_id TEXT,
    ADD COLUMN IF NOT EXISTS render_region TEXT,
    ADD COLUMN IF NOT EXISTS render_plan TEXT;

ALTER TABLE clone_instances
    ALTER COLUMN hosting_provider SET DEFAULT 'render';

UPDATE clone_instances
SET hosting_provider='render'
WHERE hosting_provider='docker'
  AND render_service_id IS NOT NULL;
