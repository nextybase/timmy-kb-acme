# AGENTS Index — Policy Comuni per Agent

Questo indice raccoglie le regole comuni che gli agent devono seguire nel repository. Evitare duplicazioni: i singoli `AGENTS.md` nelle sottocartelle devono contenere solo gli override specifici del loro ambito e rimandare qui per tutto il resto.

## Approccio operativo (AGENT-first, HiTL)

Questo repository tratta l’agente come un *teammate* con responsabilità chiare: le **policy comuni** vivono qui, gli `AGENTS.md` di area definiscono solo **override minimi** e rimandano all’indice. L’approccio è **Human-in-the-Loop**: l’agente propone micro-PR idempotenti, **non** introduce side-effects, e chiude il loop con lint/type/test.

Cardini dell’approccio:
- **SSoT & Safety** — tutte le read/write passano dalle utility e restano nel perimetro del workspace; niente effetti collaterali non dichiarati.
- **Micro-PR** — cambi piccoli, motivati, con diff chiaro; se tocchi X allinea Y/Z (docs, test, frontmatter).
- **Matrix come contratto** — questa tabella è il *punto di verità* tra aree: build/test/lint/path-safety/documentazione sono obblighi, non suggerimenti.
- **Gating UX** — nelle superfici UI le azioni seguono lo **stato** (es. la Semantica si abilita solo con RAW presente), evitando operazioni non idempotenti.

In sintesi: policy **qui**, override **nei loro AGENTS**, e l’agente lavora *on-rails* per garantire coerenza e ripetibilità.


<!-- MATRIX:BEGIN -->
> **Matrice di override (panoramica rapida)**
> Gli `AGENTS.md` locali definiscono solo le deroghe/override; le policy comuni restano in questo indice.

| Area | File | Override chiave (sintesi) | Criteri di accettazione (key) | Note |
|------|------|---------------------------|-------------------------------|------|
| Root | `AGENTS.md` | — | — |  |
| Pipeline Core | `src/pipeline/AGENTS.md` | **Path‑safety**: tutte le write/copy/rm passano da `ensure_within*` (no join manuali).; **Scritture atomiche**: `safe_write_text/bytes` obbligatorie. | Nessuna write fuori dal workspace cliente. |  |
| Semantica | `src/semantic/AGENTS.md` | **SSoT tag runtime: SQLite (`semantic/tags.db`)**; YAML `tags_reviewed.yaml` è solo authoring/migrazione.; Non importare o invocare funzioni `_private`; mantenere compatibilità della façade. | Enrichment non duplica tag, rispetta sinonimi/alias e non altera contenuti non frontmatter. |  |
| UI (Streamlit) | `src/ui/AGENTS.md` | Riferimento operativo: segui le linee guida di `docs/streamlit_ui.md` (router, stato, I/O, logging).; Gating: la tab **Semantica** si abilita **solo** quando `raw/` locale e presente. | Nessuna azione "Semantica" se RAW vuoto. | UX guidata da stato |
| Test | `tests/AGENTS.md` | Niente dipendenze di rete (Drive/Git mockati o bypass).; Contract test su guard di `book/` (solo `.md`, `.md.fp` ignorati). | Build verde locale; smoke E2E su dummy slug riproducibile. |  |
| Documentazione | `docs/AGENTS.md` | **cSpell**: eseguire `pre-commit run cspell --all-files` (o `--files docs/...`) prima del commit; aggiungere nuove parole solo se sono termini di dominio verificati.; **Frontmatter & titoli**: i file Markdown devono indicare la versione coerente; niente numerazioni divergenti tra README e docs/. | Spell check pulito su `docs/` e `README.md`, senza ignorare file. |  |
| Codex (repo) | `.codex/AGENTS.md` | **Path-safety**: scrivo solo in `src/`, `tests/`, `docs/`, `.codex/` (mai in `config/**`, `.env*`, `output/**`).; **Scritture atomiche**: temp + replace; zero side-effect a import-time. | Micro-PR: 1 change set, motivazione chiara, diff minimale; se tocco X aggiorno docs Y/Z. |  |

<!-- MATRIX:END -->


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
- Codex (repo): `.codex/AGENTS.md`

---

## Nota anti‑duplicazione
- Le sezioni comuni vivono in questo indice.
- I file `AGENTS.md` locali devono contenere solo regole/deroghe specifiche del loro ambito (es. vincoli UI, contratti semantici, piramide test), con un link esplicito a questo indice.
