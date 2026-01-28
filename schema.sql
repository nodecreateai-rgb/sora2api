-- Supabase PostgreSQL Schema for Sora2API
-- This file contains all table definitions compatible with Supabase

-- Enable UUID extension (if needed)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tokens table
CREATE TABLE IF NOT EXISTS tokens (
    id SERIAL PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    st TEXT,
    rt TEXT,
    client_id TEXT,
    proxy_url TEXT,
    remark TEXT,
    expiry_time TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    cooled_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    use_count INTEGER DEFAULT 0,
    plan_type TEXT,
    plan_title TEXT,
    subscription_end TIMESTAMP,
    sora2_supported BOOLEAN,
    sora2_invite_code TEXT,
    sora2_redeemed_count INTEGER DEFAULT 0,
    sora2_total_count INTEGER DEFAULT 0,
    sora2_remaining_count INTEGER DEFAULT 0,
    sora2_cooldown_until TIMESTAMP,
    image_enabled BOOLEAN DEFAULT TRUE,
    video_enabled BOOLEAN DEFAULT TRUE,
    image_concurrency INTEGER DEFAULT -1,
    video_concurrency INTEGER DEFAULT -1,
    is_expired BOOLEAN DEFAULT FALSE
);

-- Token stats table
CREATE TABLE IF NOT EXISTS token_stats (
    id SERIAL PRIMARY KEY,
    token_id INTEGER NOT NULL,
    image_count INTEGER DEFAULT 0,
    video_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMP,
    today_image_count INTEGER DEFAULT 0,
    today_video_count INTEGER DEFAULT 0,
    today_error_count INTEGER DEFAULT 0,
    today_date DATE,
    consecutive_error_count INTEGER DEFAULT 0,
    FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    token_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    progress FLOAT DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    result_urls TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
);

-- Request logs table
CREATE TABLE IF NOT EXISTS request_logs (
    id SERIAL PRIMARY KEY,
    token_id INTEGER,
    task_id TEXT,
    operation TEXT NOT NULL,
    request_body TEXT,
    response_body TEXT,
    status_code INTEGER NOT NULL,
    duration FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE SET NULL
);

-- Admin config table
CREATE TABLE IF NOT EXISTS admin_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    admin_username TEXT DEFAULT 'admin',
    admin_password TEXT DEFAULT 'admin',
    api_key TEXT DEFAULT 'han1234',
    error_ban_threshold INTEGER DEFAULT 3,
    task_retry_enabled BOOLEAN DEFAULT TRUE,
    task_max_retries INTEGER DEFAULT 3,
    auto_disable_on_401 BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT admin_config_single_row CHECK (id = 1)
);

-- Admin sessions table (for persistent admin tokens)
CREATE TABLE IF NOT EXISTS admin_sessions (
    token TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires_at ON admin_sessions(expires_at);

-- Proxy config table
CREATE TABLE IF NOT EXISTS proxy_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    proxy_enabled BOOLEAN DEFAULT FALSE,
    proxy_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT proxy_config_single_row CHECK (id = 1)
);

-- Watermark-free config table
CREATE TABLE IF NOT EXISTS watermark_free_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    watermark_free_enabled BOOLEAN DEFAULT FALSE,
    parse_method TEXT DEFAULT 'third_party',
    custom_parse_url TEXT,
    custom_parse_token TEXT,
    fallback_on_failure BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT watermark_free_config_single_row CHECK (id = 1)
);

-- Cache config table
CREATE TABLE IF NOT EXISTS cache_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    cache_enabled BOOLEAN DEFAULT FALSE,
    cache_timeout INTEGER DEFAULT 600,
    cache_base_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT cache_config_single_row CHECK (id = 1)
);

-- Generation config table
CREATE TABLE IF NOT EXISTS generation_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    image_timeout INTEGER DEFAULT 300,
    video_timeout INTEGER DEFAULT 3000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT generation_config_single_row CHECK (id = 1)
);

-- Token refresh config table
CREATE TABLE IF NOT EXISTS token_refresh_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    at_auto_refresh_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT token_refresh_config_single_row CHECK (id = 1)
);

-- Call logic config table
CREATE TABLE IF NOT EXISTS call_logic_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    call_mode TEXT DEFAULT 'default',
    polling_mode_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT call_logic_config_single_row CHECK (id = 1)
);

-- POW proxy config table
CREATE TABLE IF NOT EXISTS pow_proxy_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    pow_proxy_enabled BOOLEAN DEFAULT FALSE,
    pow_proxy_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pow_proxy_config_single_row CHECK (id = 1)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_task_id ON tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_token_active ON tokens(is_active);
CREATE INDEX IF NOT EXISTS idx_token_email ON tokens(email);
CREATE INDEX IF NOT EXISTS idx_token_stats_token_id ON token_stats(token_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_token_id ON request_logs(token_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);

-- Row Level Security (RLS) policies for Supabase (optional, can be enabled if needed)
-- ALTER TABLE tokens ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE token_stats ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE request_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE admin_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE proxy_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE watermark_free_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE cache_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE generation_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE token_refresh_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE call_logic_config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE pow_proxy_config ENABLE ROW LEVEL SECURITY;
