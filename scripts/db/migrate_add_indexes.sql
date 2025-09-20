-- Migrazione indici/unique per idempotenza su tabella chunks
BEGIN;
CREATE INDEX IF NOT EXISTS idx_chunks_project_scope ON chunks(project_slug, scope);
CREATE UNIQUE INDEX IF NOT EXISTS ux_chunks_natural ON chunks(project_slug, scope, path, version, content);
COMMIT;
