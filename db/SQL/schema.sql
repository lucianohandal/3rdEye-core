CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    price NUMERIC NOT NULL,
    available BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_plan_id
ON plans (id);

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID REFERENCES plans(id),
    status TEXT NOT NULL DEFAULT 'disabled',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disabled_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_org_id
ON organizations (id);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disabled_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_users_id
ON users (id);

CREATE INDEX IF NOT EXISTS idx_users_org_id
ON users (org_id);

CREATE TABLE IF NOT EXISTS holidays (
    holiday_date DATE PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    api_key UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL,
    display_prefix TEXT NOT NULL,
    name TEXT NULL,
    scopes TEXT[] NOT NULL DEFAULT ARRAY['logs:write'],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    last_used_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_api_key
ON api_keys (api_key);

CREATE INDEX IF NOT EXISTS idx_api_keys_org_id
ON api_keys (org_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        WHERE typname = 'log_level_smallint'
    ) THEN
        CREATE DOMAIN log_level_smallint AS SMALLINT
        CHECK (VALUE IN (10, 20, 30, 40, 50));
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS log_signatures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    template TEXT NOT NULL,
    line SMALLINT NOT NULL,
    file TEXT NOT NULL,
    method TEXT NOT NULL,
    first_appearance_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_appearance_commit TEXT,
    log_level log_level_smallint NOT NULL,

    UNIQUE (org_id, template, line, file, method)
);

CREATE INDEX IF NOT EXISTS idx_log_signatures_id
ON log_signatures (org_id, id);

CREATE INDEX IF NOT EXISTS idx_log_signatures_org_template_file_method
ON log_signatures (org_id, template, file, method);

CREATE INDEX IF NOT EXISTS idx_log_signatures_org_template_line_file_method
ON log_signatures (org_id, template, line, file, method);

CREATE TABLE IF NOT EXISTS raw_logs (
    message TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stack TEXT,

    -- DB Metadata
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    signature_id UUID NULL REFERENCES log_signatures(id) ON DELETE CASCADE,

    -- Environment Metadata
    service VARCHAR(255),
    environment VARCHAR(100),
    version VARCHAR(100),
    git_sha VARCHAR(100),

    -- Correlation Metadata
    trace_id VARCHAR(255),
    span_id VARCHAR(255),
    request_id VARCHAR(255),
    user_id VARCHAR(255),

    attributes JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_timestamp
ON raw_logs (org_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_message_trgm
ON raw_logs USING GIN (message gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_signature_timestamp
ON raw_logs (org_id, signature_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_service_timestamp
ON raw_logs (org_id, service, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_environment_timestamp
ON raw_logs (org_id, environment, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_trace_id
ON raw_logs (org_id, trace_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_span_id
ON raw_logs (org_id, span_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_request_id
ON raw_logs (org_id, request_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_logs_org_user_id
ON raw_logs (org_id, user_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    severity SMALLINT NOT NULL,
    message TEXT NOT NULL,
    observed_value DOUBLE PRECISION,
    expected_value DOUBLE PRECISION,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ NULL,
    CONSTRAINT valid_severity CHECK (severity IN (10, 20, 30, 40, 50))
);

CREATE INDEX IF NOT EXISTS idx_alerts_open_project_severity_created_at
ON alerts (org_id, severity DESC, created_at DESC)
WHERE closed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_alerts_closed_project_severity_created_at
ON alerts (org_id, severity DESC, created_at DESC)
WHERE closed_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS log_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    time_window TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
--     log_count INT NOT NULL DEFAULT 0,
    seasonality TEXT[] NULL,
    claimed_at TIMESTAMPTZ NULL DEFAULT NULL,
    processed_at TIMESTAMPTZ NULL DEFAULT NULL,

    CONSTRAINT valid_window CHECK (time_window IN ('xs', 's', 'm', 'l', 'xl', 'xxl')),

    UNIQUE (org_id, time_window, start_time)
);

CREATE TABLE IF NOT EXISTS log_summary_signatures (

    summary_id UUID NOT NULL REFERENCES log_summaries(id) ON DELETE CASCADE,
    log_signature_id UUID NOT NULL REFERENCES log_signatures(id) ON DELETE CASCADE,
    log_level log_level_smallint NOT NULL,
    log_count INT NOT NULL DEFAULT 0,

    PRIMARY KEY (summary_id, log_signature_id)
);

CREATE TABLE IF NOT EXISTS metric_baselines (
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    time_window TEXT NOT NULL,
    seasonality_key TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    mean DOUBLE PRECISION NOT NULL DEFAULT 0,
    m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_metric_baseline_window CHECK (time_window IN ('xs', 's', 'm', 'l', 'xl', 'xxl')),

    PRIMARY KEY (org_id, time_window, seasonality_key, metric_key)
);

CREATE TABLE IF NOT EXISTS time_window_sizes (
    size TEXT PRIMARY KEY,
    time_delta INTERVAL NOT NULL
);
