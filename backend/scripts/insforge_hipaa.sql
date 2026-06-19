-- Scalpel HIPAA-oriented hardening for Insforge Postgres
-- Apply after insforge_schema.sql. Service-role API access bypasses RLS;
-- these policies block direct anon/authenticated REST access to PHI tables.

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    resource_type TEXT,
    resource_id TEXT,
    case_id TEXT,
    ip_address INET,
    user_agent TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_case ON audit_events(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type);

-- Deny direct client access to PHI tables (service role used by FastAPI bypasses RLS).
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'cases', 'checklists', 'session_logs', 'case_documents',
        'compact_context', 'snippets', 'audit_events'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS deny_anon ON %I', tbl);
        EXECUTE format(
            'CREATE POLICY deny_anon ON %I FOR ALL TO anon USING (false) WITH CHECK (false)',
            tbl
        );
        EXECUTE format('DROP POLICY IF EXISTS deny_authenticated ON %I', tbl);
        EXECUTE format(
            'CREATE POLICY deny_authenticated ON %I FOR ALL TO authenticated USING (false) WITH CHECK (false)',
            tbl
        );
    END LOOP;
END $$;
