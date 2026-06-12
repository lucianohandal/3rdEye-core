CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
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
ON alerts (project_id, severity DESC, created_at DESC)
WHERE closed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_alerts_closed_project_severity_created_at
ON alerts (project_id, severity DESC, created_at DESC)
WHERE closed_at IS NOT NULL;