# Codex – Checklist di accettazione

- [ ] Path-safety rispettata (scrivo solo in `src/`, `docs/`, `.codex/`; **mai** in `config/**`, `.env*`, `output/**`)
- [ ] Scritture atomiche (temp + replace), zero side-effect a import-time
- [ ] QA locale eseguito: `isort` → `black` → `ruff --fix` → `mypy` → `pytest -q -k 'not slow'`
- [ ] Micro-PR: 1 change set, motivazione chiara, diff minimale; se tocco X aggiorno anche docs Y/Z
- [ ] UI: messaggi brevi; salvataggi solo via utility SSoT (no `Path.write_text` diretto)
