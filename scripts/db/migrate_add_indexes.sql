-- Migrazione indici/unique per idempotenza su tabella chunks
BEGIN;
CREATE INDEX IF NOT EXISTS idx_chunks_slug_scope ON chunks(slug, scope);
CREATE UNIQUE INDEX IF NOT EXISTS ux_chunks_natural ON chunks(slug, scope, path, version, content);
COMMIT;
