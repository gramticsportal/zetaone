-- P3: Add missing spec fields to verdicts and audit_events tables.
-- Safe to run multiple times (IF NOT EXISTS guards).

-- verdicts: add tenant_id, policy_pack_id, processing_time_ms, expiration_timestamp
ALTER TABLE verdicts
    ADD COLUMN IF NOT EXISTS tenant_id        UUID REFERENCES tenants(id),
    ADD COLUMN IF NOT EXISTS policy_pack_id   VARCHAR(255),
    ADD COLUMN IF NOT EXISTS processing_time_ms INTEGER,
    ADD COLUMN IF NOT EXISTS expiration_timestamp TIMESTAMPTZ;

-- audit_events: add actor, action, before/after state, ip, user_agent, correlation_id, tenant_id
ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS tenant_id       UUID,
    ADD COLUMN IF NOT EXISTS action          VARCHAR(128),
    ADD COLUMN IF NOT EXISTS actor           JSONB,
    ADD COLUMN IF NOT EXISTS before_state    JSONB,
    ADD COLUMN IF NOT EXISTS after_state     JSONB,
    ADD COLUMN IF NOT EXISTS ip_address      VARCHAR(64),
    ADD COLUMN IF NOT EXISTS user_agent      VARCHAR(512),
    ADD COLUMN IF NOT EXISTS correlation_id  UUID;

-- Index for fast tenant-scoped verdict queries
CREATE INDEX IF NOT EXISTS idx_verdicts_tenant_id ON verdicts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_verdicts_policy_pack_id ON verdicts(policy_pack_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_id ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_correlation_id ON audit_events(correlation_id);
