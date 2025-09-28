# Prompt riusabili (per Agent/Chat IDE)

## Doc-sync (API o flow cambiati)
Sistema la documentazione in modo idempotente:
- Leggi `docs/architecture.md`, `docs/developer_guide.md`, `docs/guida_ui.md`.
- Confronta con il codice attuale.
- Applica patch minime e precise (no riscritture ampie).
- Aggiorna anche `.codex/WORKFLOWS.md` se serve.
- Verifica cSpell e link interni.

## Hardening I/O
Controlla path‑safety e scritture atomiche:
- Sostituisci join manuali con util SSoT.
- Inserisci guard su directory target e slug.
- Aggiungi test unit per i casi limite.

## Enrichment frontmatter
Verifica arricchimento usando **SQLite** (`semantic/tags.db`); YAML è solo authoring/migrazione.
Se `tags.db` assente: proponi migrazione o rigenerazione safe.

## cSpell cleanup su docs/
- Raccogli parole ignote; aggiorna `cspell.json` e `.vscode/settings.json`.
- Evita ignore per‑file se non necessario.

### Micro-PR Commit Template
Titolo: <breve, imperativo>
Motivazione: <bugfix/security/robustezza; impatto>
Scope: <file toccati e perché; 1 change set>
Regole rispettate: path-safety ✔ / atomiche ✔ / no side-effects a import-time ✔
Test: <nuovi/aggiornati; come riprodurre — es. pytest -k ...>
QA: isort → black → ruff --fix → mypy → pytest
Note docs: <se tocchi X, aggiorna Y/Z>
