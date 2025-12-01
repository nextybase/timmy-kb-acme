# Checklist operative

## PR / Commit
- Messaggi conventional (feat/fix/docs/chore). Descrivi Cosa/Perche'/Come.
- Test minimi aggiornati; build verde; linter ok.
- Se tocchi firme/flow: aggiorna **docs** (+ note migrazione).
- 0 warning cSpell in `docs/`.

### Revisione con Senior Reviewer
- [ ] Per modifiche non banali (new feature, logica di sicurezza/I/O, integrazioni) ho usato il prompt "Dev task con review del Senior" in `.codex/PROMPTS.md` prima di chiedere aiuto a Codex.
- [ ] Ho preparato un messaggio di riepilogo seguendo il prompt "Preparare la richiesta di review per il Senior".
- [ ] Ho condiviso con il Senior contesto del task, sintesi dei cambi, esito della pipeline QA e i dubbi/trade-off principali.
- [ ] Ho applicato (o discusso) i feedback del Senior prima del merge su branch protette.

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
- **[BLOCKING]** Se cambi firme, flussi o UX: aggiorna **architecture.md / developer_guide.md / guida_ui.md** (o altri doc interessati). Nessun merge senza nota esplicita nella PR.
- Documenta sempre le modifiche alla pipeline anche in `.codex/WORKFLOWS.md` / Runbook quando necessario.
- Nel testo della PR inserisci la sezione `Docs:` elencando i file aggiornati (o `n/a` solo se davvero non servono update).
