CREATE TABLE IF NOT EXISTS bot_user_blocks (
    user_id BIGINT PRIMARY KEY,
    blocked_by BIGINT NOT NULL,
    blocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
    id BIGSERIAL PRIMARY KEY,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scheduled_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','sending','completed','partial','failed','cancelled')),
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_scheduled_broadcasts_due
    ON scheduled_broadcasts(status, scheduled_at, id);

ALTER TABLE clone_instances
    ADD COLUMN IF NOT EXISTS bot_name TEXT,
    ADD COLUMN IF NOT EXISTS repository_url TEXT,
    ADD COLUMN IF NOT EXISTS image_ref TEXT,
    ADD COLUMN IF NOT EXISTS hosting_provider TEXT NOT NULL DEFAULT 'docker',
    ADD COLUMN IF NOT EXISTS encrypted_environment TEXT;
