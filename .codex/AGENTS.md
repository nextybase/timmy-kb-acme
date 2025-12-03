# Codex - Checklist di accettazione

- Prima di qualsiasi intervento, apri e rileggi `docs/runbook_codex.md`.

## Regole
- **Path-safety**: scrivo solo in `src/`, `tests/`, `docs/`, `.codex/` (mai in `config/**`, `.env*`, `output/**`).
- **Scritture atomiche**: temp + replace; zero side-effect a import-time.
- **QA pipeline**: `isort`  `black`  `ruff --fix`  `mypy`  `pytest -q -k 'not slow'`.
- **SSoT**: salvataggi solo via utility (`ensure_within*`, `safe_write_*`), no `Path.write_text/bytes`.
- **GitHub orchestration**: per i push usare gli helper interni (`_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`) e nei test stubbare `_prepare_repo`/`_stage_changes` come in `tests/pipeline/test_github_push.py`.
- **Vision tooling**: riusare `_is_gate_error` esposto da `ui.pages.tools_check` e i builder `build_payload/emit_structure` di `tools.gen_dummy_kb` al posto dei vecchi inline helper.

## Accettazione
- Micro-PR: 1 change set, motivazione chiara, diff minimale; se tocco X aggiorno docs Y/Z.

- [ ] Path-safety rispettata (scrivo solo in `src/`, `tests/`, `docs/`, `.codex/`; **mai** in `config/**`, `.env*`, `output/**`)
- [ ] Scritture atomiche (temp + replace), zero side-effect a import-time
- [ ] QA locale eseguito: `isort`  `black`  `ruff --fix`  `mypy`  `pytest -q -k 'not slow'`
- [ ] Micro-PR: 1 change set, motivazione chiara, diff minimale; se tocco X aggiorno anche docs Y/Z
- [ ] UI: messaggi brevi; salvataggi solo via utility SSoT (no `Path.write_text` diretto)

## Collaborazione con Senior Reviewer
- L'agente Codex lavora a supporto dello sviluppatore umano (Franco / team) e del Senior Reviewer esterno (AI esterna) per mantenere allineata la qualita NeXT.
- Quando e prevista una review esterna Codex DEVE:
  1. Preparare un riepilogo sintetico con contesto del task, file toccati e perche la soluzione rispetta `.codex/CONSTITUTION.md` e `docs/AGENTS_INDEX.md`.
  2. Limitare lo scope: micro-PR che affrontano un singolo problema e nessun refactor massivo non richiesto.
  3. Eseguire la pipeline QA locale standard (formatter, linter, type-checker, test) e riportare esplicitamente l'esito nel messaggio al Senior.
  4. Esplicitare dubbi, trade-off, TODO e problemi noti, inclusi test falliti o limiti della soluzione, prima di inoltrare la review.
