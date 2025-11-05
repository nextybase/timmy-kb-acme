# Codex - Checklist di accettazione

- Prima di qualsiasi intervento, apri e rileggi `docs/runbook_codex.md`.

## Regole
- **Path-safety**: scrivo solo in `src/`, `tests/`, `docs/`, `.codex/` (mai in `config/**`, `.env*`, `output/**`).
- **Scritture atomiche**: temp + replace; zero side-effect a import-time.
- **QA pipeline**: `isort` → `black` → `ruff --fix` → `mypy` → `pytest -q -k 'not slow'`.
- **SSoT**: salvataggi solo via utility (`ensure_within*`, `safe_write_*`), no `Path.write_text/bytes`.
- **GitHub orchestration**: per i push usare gli helper interni (`_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`) e nei test stubbare `_prepare_repo`/`_stage_changes` come in `tests/pipeline/test_github_push.py`.
- **Vision tooling**: riusare `_is_gate_error` esposto da `ui.pages.tools_check` e i builder `build_payload/emit_structure` di `tools.gen_dummy_kb` al posto dei vecchi inline helper.

## Accettazione
- Micro-PR: 1 change set, motivazione chiara, diff minimale; se tocco X aggiorno docs Y/Z.

- [ ] Path-safety rispettata (scrivo solo in `src/`, `tests/`, `docs/`, `.codex/`; **mai** in `config/**`, `.env*`, `output/**`)
- [ ] Scritture atomiche (temp + replace), zero side-effect a import-time
- [ ] QA locale eseguito: `isort` → `black` → `ruff --fix` → `mypy` → `pytest -q -k 'not slow'`
- [ ] Micro-PR: 1 change set, motivazione chiara, diff minimale; se tocco X aggiorno anche docs Y/Z
- [ ] UI: messaggi brevi; salvataggi solo via utility SSoT (no `Path.write_text` diretto)
