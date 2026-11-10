CREATE TABLE IF NOT EXISTS manager_fsub_channels (
    channel_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    join_url TEXT NOT NULL,
    added_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
