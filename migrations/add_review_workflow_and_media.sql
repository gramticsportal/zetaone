-- Review workflow + media persistence + asset lineage.
-- Run for existing DBs (new DBs get this via create_all_tables).

-- Assets: media, lineage, client correlation, review lifecycle
ALTER TABLE assets ADD COLUMN IF NOT EXISTS storage_uri VARCHAR(1024);
ALTER TABLE assets ADD COLUMN IF NOT EXISTS external_ref VARCHAR(255);
ALTER TABLE assets ADD COLUMN IF NOT EXISTS parent_asset_id UUID REFERENCES assets(id);
ALTER TABLE assets ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS review_state VARCHAR(32);

CREATE INDEX IF NOT EXISTS ix_assets_status ON assets (status);
CREATE INDEX IF NOT EXISTS ix_assets_review_state ON assets (review_state);
CREATE INDEX IF NOT EXISTS ix_assets_external_ref ON assets (external_ref);
CREATE INDEX IF NOT EXISTS ix_assets_parent_asset_id ON assets (parent_asset_id);
CREATE INDEX IF NOT EXISTS ix_assets_created_at ON assets (created_at);

-- Review decisions: recorded human verdicts + per-violation labels
CREATE TABLE IF NOT EXISTS review_decisions (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES assets(id),
    verdict_id UUID REFERENCES verdicts(id),
    tenant_id UUID REFERENCES tenants(id),
    reviewer VARCHAR(255) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    reason TEXT,
    violation_feedback JSONB NOT NULL DEFAULT '[]',
    source VARCHAR(32) NOT NULL DEFAULT 'human_review',
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_review_decisions_asset_id ON review_decisions (asset_id);
CREATE INDEX IF NOT EXISTS ix_review_decisions_decision ON review_decisions (decision);
CREATE INDEX IF NOT EXISTS ix_review_decisions_created_at ON review_decisions (created_at);
