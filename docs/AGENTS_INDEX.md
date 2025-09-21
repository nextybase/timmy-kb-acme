# AGENTS Index — Policy Comuni per Agent

Questo indice raccoglie le regole comuni che gli agent devono seguire nel repository. Evitare duplicazioni: i singoli `AGENTS.md` nelle sottocartelle devono contenere solo gli override specifici del loro ambito e rimandare qui per tutto il resto.

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
