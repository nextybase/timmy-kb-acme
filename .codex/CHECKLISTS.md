# Checklist operative

## PR / Commit
- Messaggi conventional (feat/fix/docs/chore). Descrivi Cosa/Perche'/Come.
- Test minimi aggiornati; build verde; linter ok.
- Se tocchi firme/flow: aggiorna **docs** (+ note migrazione).
- 0 warning cSpell in `docs/`.

## Sicurezza & I/O
- Path validati (ensure_within); nessuna write "a mano".
- Scritture atomiche; rollback definito su errori.

## Pre-commit policies
- Nessun `assert` runtime in `src/` (solo nei test). Hook: `forbid-runtime-asserts`.
- Nessun `Path.write_text/bytes` in `src/`. Usa `safe_write_text/bytes` + `ensure_within`. Hook: `forbid-path-write-text-bytes`.
- Guard-rail SSoT: prima di ogni write/copy/delete chiama `ensure_within(base, target)`.

## UI / Workflow
- Gating tab **Semantica** -> `raw/` presente.
- Preview Docker: valida porta (1..65535) e `container_name` sicuro.
- **SSoT tag runtime**: `semantic/tags.db` presente/aggiornato.

## Drive/Git
- Drive: credenziali/ID presenti prima di lanciare il runner.
- Push: solo `.md` da `book/`; escludi `.md.fp` e binari.

## Multi-agent alignment
- Allinea i flag condivisi (`TIMMY_NO_GITHUB`, `GIT_DEFAULT_BRANCH`, `GIT_FORCE_ALLOWED_BRANCHES`, `TAGS_MODE`, `ui.skip_preflight`) tra CLI, UI e agent: aggiorna `.env.sample`/docs se cambiano.
- Verifica che i servizi in UI siano caricati (`ui.services.tags_adapter`, drive runner). Se un adapter manca, assicurati che la UI mostri help e fallback (modalita' stub).
- Monitora la telemetria strutturata: tutte le pipeline devono emettere `phase_scope` coerenti (prepare_repo/stage_changes/push_with_retry o force_push) e rispettare `LeaseLock`.
- Controlla le impostazioni di throttling/cache (`NLP_THREADS`, `TIMMY_SAFE_PDF_CACHE_TTL`, cache clients_db) per evitare fork divergenti fra agent e orchestratori.

## Documentazione
- Allinea **architecture.md / developer_guide.md / guida_ui.md** per ogni cambio funzionale.
- Aggiorna `.codex/WORKFLOWS.md` se cambi pipeline.
