# Pipeline & I/O

## Task di avvio
- Leggi `docs/AGENTS_INDEX.md`, `.codex/AGENTS.md`, `.codex/CODING_STANDARDS.md`, `docs/runbook_codex.md`.
- Usa solo utility SSoT (`ensure_within*`, `safe_write_*`), scope write: `src/`, `tests/`, `docs/`, `.codex/`.

## Hardening path-safety e scritture atomiche
- Rimpiazza join manuali con `ensure_within_and_resolve`.
- Applica `safe_write_text/bytes` atomici e guard su slug/perimetro.
- Aggiungi test unit per traversal/symlink e path fuori perimetro.

## Orchestrazione GitHub (helper obbligatori)
- Usa `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`.
- Nei test stubba `_prepare_repo`/`_stage_changes` come in `tests/pipeline/test_github_push.py`.
- Log strutturato del flusso (`prepare_repo`, `stage_changes`, `push`).

## Template micro-PR
Titolo: <breve, imperativo>
Motivazione: <bugfix/security/robustezza; impatto>
Scope: <file toccati e perche; 1 change set>
Regole rispettate: path-safety / atomiche / no side-effects a import-time
Test: <nuovi/aggiornati; es. pytest -k ...>
QA: isort  black  ruff --fix  mypy  pytest
Note docs: <se tocchi X, aggiorna Y/Z>

## Onboarding Task Codex
- Leggi obbligatoriamente i 3 SSoT prima di ogni intervento: `docs/AGENTS_INDEX.md`, `AGENTS.md` locale, `.codex/AGENTS.md`.
- Prima di modificare file, proponi un piano d'azione sintetico (passi e ordine).
- Applica modello Micro-PR: scope singolo, diff minimo, idempotente, motivazione chiara.
- Checklist QA da confermare: path-safety (utility SSoT, scope `src/` `tests/` `docs/` `.codex/`), write-atomicity, logging strutturato, aggiornare la matrice AGENTS se toccati gli `AGENTS.md`, aggiornare documentazione se necessario, rispetto degli override specifici dell'area.

# Semantica & tags.db

## Task di avvio
- Leggi `docs/AGENTS_INDEX.md` e `src/semantic/AGENTS.md`.
- Verifica presenza `semantic/tags.db`; `tags_reviewed.yaml` solo per authoring/migrazione.

## Enrichment frontmatter
- Usa `semantic.api` (niente `_private`); SSoT tag in `tags.db`.
- Se `tags.db` manca: proponi migrazione/rigenerazione safe (no fallback silenzioso).
- README/SUMMARY via utility repo con fallback idempotenti.

## Allineamento facade vs servizi
- Controlla parita di firma tra `semantic.api` e servizi (`convert/frontmatter/embedding`).
- Aggiungi test di compatibilita e alias/sinonimi per tag.

# UI Streamlit

## Task di avvio
- Leggi `docs/streamlit_ui.md`, `src/ui/AGENTS.md`, `src/ui/pages/AGENTS.md`.
- Verifica gating RAW/slug, router `st.Page` + `st.navigation`, import-safe (no I/O a import).

## Router e gating onboarding
- Forza routing nativo (`st.navigation(pages).run()`), link interni con `st.page_link`.
- Gating: tab Semantica attiva solo se `raw/` presente; messaggi utente brevi, log dettagliati.
- Stato/slug tramite `ui.utils.route_state` e `ui.utils.slug`; niente query hacks.

## Sweep deprecazioni e layout
- Rimuovi `st.cache`, `st.experimental_*`, `unsafe_allow_html`, `use_container_width`.
- Layout compat con stub (evita `with col` non supportati); preferisci `st.dialog` con fallback.
- Logging `get_structured_logger("ui.<pagina>")`, senza `print()`/PII.

# Test & QA

## Task di avvio
- Leggi `docs/AGENTS_INDEX.md`, `tests/AGENTS.md`.
- Setup dataset dummy; nessuna dipendenza di rete (mock Drive/Git).

## QA pipeline
- Esegui: `isort`, `black`, `ruff --fix`, `mypy`, `pytest -q -k 'not slow'`.
- Contract test su guard `book/` (solo `.md`, ignora `.md.fp`), smoke E2E su slug dummy.

# Docs & Runbook

## Task di avvio
- Leggi `docs/runbook_codex.md`, `docs/AGENTS_INDEX.md`, `docs/AGENTS.md`.
- Mantieni frontmatter/titoli coerenti (`v1.0 Beta`), cSpell su `docs/` e `README.md`.

## Doc-sync (API o flow cambiati)
- Confronta codice vs `docs/architecture.md`, `docs/developer_guide.md`, `docs/guida_ui.md`.
- Applica patch minime; aggiorna `.codex/WORKFLOWS.md` se il flow cambia.
- Verifica cSpell e link relativi.

## cSpell cleanup su docs/
- Raccogli parole ignote; aggiorna `cspell.json` / `.vscode/settings.json` solo per termini di dominio.
- Evita ignore per file interi.

## Richiesta review al Senior Reviewer
- Output: titolo sintetico, contesto, file toccati + modifiche, esito QA (formatter/linter/type/test), test mancanti/known issues, 2-3 domande al Senior.
- Rispetta `.codex/CONSTITUTION.md`, `.codex/AGENTS.md`, `docs/AGENTS_INDEX.md`; scope micro-PR.
