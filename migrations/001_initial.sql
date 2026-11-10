CREATE TABLE IF NOT EXISTS bot_message_templates (
    clone_id TEXT NOT NULL, template_key TEXT NOT NULL, body TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (clone_id, template_key)
);
CREATE TABLE IF NOT EXISTS bot_message_buttons (
    clone_id TEXT NOT NULL, template_key TEXT NOT NULL, buttons JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (clone_id, template_key)
);
CREATE TABLE IF NOT EXISTS bot_users (
    clone_id TEXT NOT NULL, user_id BIGINT NOT NULL, first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(), is_banned BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (clone_id, user_id)
);
CREATE TABLE IF NOT EXISTS clone_instances (
    clone_id TEXT PRIMARY KEY, owner_id BIGINT NOT NULL, product TEXT NOT NULL CHECK(product IN ('file','link')),
    bot_id BIGINT NOT NULL UNIQUE, bot_username TEXT NOT NULL, encrypted_token TEXT NOT NULL, container_id TEXT,
    status TEXT NOT NULL, image_digest TEXT, error_code TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_clone_owner ON clone_instances(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS bot_settings (
    setting_key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
