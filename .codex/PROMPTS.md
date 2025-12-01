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

## Prompts per collaborazione con Senior Reviewer

### 1. Dev task con review del Senior
- Scopo: prompt da usare quando lo sviluppatore richiede una modifica sapendo che il lavoro riceverà review dal Senior Reviewer esterno.
> Repo `nextybase/timmy-kb-acme`
> Obiettivi:
> - implementare la modifica richiesta con approccio minimo ma completo;
> - rispettare rigorosamente `.codex/CONSTITUTION.md`, `.codex/AGENTS.md` e `docs/AGENTS_INDEX.md`;
> - predisporre il lavoro per facilitare la revisione del Senior Reviewer.
> Regole operative:
> - modificare solo le path consentite dal contratto degli agent;
> - usare sempre le utility di I/O sicure (safe write, `ensure_within*`, ecc.);
> - mantenere i cambi idempotenti, locali, da micro-PR;
> - eseguire la pipeline QA definita nel progetto (formatter, linter, type-checker, test).
> Output richiesto:
> 1. Sintesi del task (1–3 frasi).
> 2. Elenco file toccati con spiegazione per ciascuno.
> 3. Diff logico principale (non il diff completo).
> 4. Esito QA: comandi usati + risultato.
> 5. Rischi/dubbi da condividere col Senior.

### 2. Preparare la richiesta di review per il Senior
- Scopo: prompt da usare per chiedere a Codex di produrre il messaggio destinato al Senior Reviewer esterno con il riepilogo del lavoro.
> Contesto:
> - repo `nextybase/timmy-kb-acme`;
> - esiste già una branch di lavoro con i cambi.
> Obiettivo:
> - generare un messaggio chiaro e completo da inviare al Senior Reviewer esterno.
> Il messaggio deve includere:
> - titolo sintetico del cambiamento;
> - contesto (perché è stato fatto);
> - elenco file toccati + principali modifiche per ciascun file;
> - esito QA (formatter, linter, type-checker, test eseguiti e risultato);
> - eventuali test mancanti o known issues;
> - 2–3 domande precise per il Senior (es. dubbi architetturali, rischi o alternative scartate).
