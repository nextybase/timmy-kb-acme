# Checklist operative

## PR / Commit
- Messaggi conventional (feat/fix/docs/chore). Descrivi Cosa/Perché/Come.
- Test minimi aggiornati; build verde; linter ok.
- Se tocchi firme/flow: aggiorna **docs** (+ note migrazione).
- 0 warning cSpell in `docs/`.

## Sicurezza & I/O
- Path validati (ensure_within); nessuna write “a mano”.
- Scritture atomiche; rollback definito su errori.

## Pre-commit policies
- Nessun `assert` runtime in `src/` (solo nei test). Hook: `forbid-runtime-asserts`.
- Nessun `Path.write_text/bytes` in `src/`. Usa `safe_write_text/bytes` + `ensure_within`. Hook: `forbid-path-write-text-bytes`.
- Guard-rail SSoT: prima di ogni write/copy/delete chiama `ensure_within(base, target)`.

## UI / Workflow
- Gating tab **Semantica** → `raw/` presente.
- Preview Docker: valida porta (1..65535) e `container_name` sicuro.
- **SSoT tag runtime**: `semantic/tags.db` presente/aggiornato.

## Drive/Git
- Drive: credenziali/ID presenti prima di lanciare il runner.
- Push: solo `.md` da `book/`; escludi `.md.fp` e binari.

## Documentazione
- Allinea **architecture.md / developer_guide.md / guida_ui.md** per ogni cambio funzionale.
- Aggiorna `.codex/WORKFLOWS.md` se cambi pipeline.
