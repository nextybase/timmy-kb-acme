# AGENTS Index — Policy Comuni per Agent

Questo indice raccoglie le regole comuni che gli agent devono seguire nel repository. Evitare duplicazioni: i singoli `AGENTS.md` nelle sottocartelle devono contenere solo gli override specifici del loro ambito e rimandare qui per tutto il resto.

> **Matrice di override (panoramica rapida)**
> Gli `AGENTS.md` locali definiscono solo le deroghe/override specifiche di area; le policy comuni restano in questo indice.

| Area               | File                           | Override chiave (sintesi)                                                                 | Criteri di accettazione (key)                                  | Note                           |
|--------------------|--------------------------------|-------------------------------------------------------------------------------------------|-----------------------------------------------------------------|--------------------------------|
| Root               | `AGENTS.md`                    | Indice generale e rimandi a `.codex/*`; **nessun override tecnico**                      | —                                                               | Hub di navigazione             |
| Pipeline Core      | `src/pipeline/AGENTS.md`       | **Path-safety** via `ensure_within*`; **scritture atomiche** `safe_write_*`; logging/redazione | No write fuori workspace; operazioni **idempotenti**            | Safety prima di tutto          |
| Semantica          | `src/semantic/AGENTS.md`       | **SSoT tag su SQLite** (`semantic/tags.db`); usare solo **façade `semantic.api`**; no `_private`; no side-effects a import-time | Niente duplicazioni tag; frontmatter integro; se assente DB → proporre migrazione | Contratti stabili              |
| UI (Streamlit)     | `src/ui/AGENTS.md`             | **Gating**: tab *Semantica* attiva solo con `raw/` presente; persistenza solo via util SSoT; messaggi brevi | Nessuna azione “Semantica” se `raw/` vuoto; feedback chiaro     | UX guidata da stato            |
| Test               | `tests/AGENTS.md`              | Piramide test; niente rete; **contract guard** su `book/`                                 | Build verde; smoke E2E su dummy slug                            | Dati sintetici, riproducibili  |
| Documentazione     | `docs/AGENTS.md`               | **(Da allineare)**: oggi duplica “Test”; attese regole su cSpell/frontmatter/ADR          | —                                                               | TODO: specificare override doc |
| Codex (repo)       | `.codex/AGENTS.md`             | Checklist pre-push: path-safety, atomiche, QA chain, micro-PR                             | —                                                               | Enforcement operativo          |
| Personale (utente) | `~/.codex/AGENTS.md` *(local)* | Preferenze individuali (stile, diff, micro-PR)                                            | —                                                               | **Non versionato**             |


---

## Policy comuni
- Build
  - Mantieni gli script/target di build idempotenti e ripetibili.
  - Non introdurre effetti collaterali globali o modifiche di stato non dichiarate.
- Test
  - Esegui test locali in modo deterministico; niente dipendenze di rete nei test unit.
  - Usa marker/filtri per isolare aree (es. `-m drive`, `-m push`, `-m slow`).
- Lint & Type‑check
  - Applica i linters configurati (Ruff/Black/isort) e il type‑check (mypy/pyright) quando presenti.
  - Non alterare gli standard del progetto; rispetta le regole già in `pyproject.toml`.
- Path‑safety & I/O
  - Qualsiasi lettura/scrittura deve passare dalle utility SSoT (`ensure_within*`, `safe_write_*`).
  - Vietato creare/cancellare file fuori dal perimetro del workspace cliente.
- Documentazione & QA
  - Aggiorna la documentazione quando cambi UX/flow.
  - Mantieni cSpell pulito sulle path previste; aggiorna i dizionari solo per termini tecnici/di dominio.

---

## Rimandi (AGENTS locali)
- Pipeline Core: `src/pipeline/AGENTS.md`
- Semantica: `src/semantic/AGENTS.md`
- UI (Streamlit): `src/ui/AGENTS.md`
- Test: `tests/AGENTS.md`
- Documentazione: `docs/AGENTS.md`
- Radice progetto: `AGENTS.md`

---

## Nota anti‑duplicazione
- Le sezioni comuni vivono in questo indice.
- I file `AGENTS.md` locali devono contenere solo regole/deroghe specifiche del loro ambito (es. vincoli UI, contratti semantici, piramide test), con un link esplicito a questo indice.
