-- P8: Webhooks table for compliance event notifications.
-- Safe to run multiple times (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS webhooks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID REFERENCES tenants(id) ON DELETE CASCADE,
    url                 VARCHAR(2048) NOT NULL,
    secret              VARCHAR(128),              -- HMAC-SHA256 signing secret; never returned in API
    events              JSONB NOT NULL DEFAULT '[]'::JSONB,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_triggered_at   TIMESTAMPTZ,
    last_status_code    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_webhooks_tenant_id  ON webhooks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_is_active  ON webhooks(is_active) WHERE is_active = TRUE;
