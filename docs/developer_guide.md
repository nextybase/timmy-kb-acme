# Developer Guide

> Questa guida descrive regole, flussi e convenzioni per contribuire a **timmy‑kb**. È orientata a uno sviluppo rigoroso, idempotente e sicuro sul filesystem.

---

## Indice
- [Architettura in breve](#architettura-in-breve)
- [Fasi operative e façade `semantic.api`](#fasi-operative-e-façade-semanticapi)
- [Regole di sicurezza I/O e path-safety](#regole-di-sicurezza-io-e-path-safety)
- [Gestione errori, exit codes e osservabilità](#gestione-errori-exit-codes-e-osservabilità)
- [Conversione Markdown: policy ufficiale](#conversione-markdown-policy-ufficiale)
- [Enrichment & vocabolario: comportamento fail‑fast](#enrichment--vocabolario-comportamento-fail-fast)
- [Indexer & KPI DB (inserimenti reali)](#indexer--kpi-db-inserimenti-reali)
- [UI: tab Finanza (I/O sicuro e cleanup)](#ui-tab-finanza-io-sicuro-e-cleanup)
- [Tooling: `gen_dummy_kb.py` e `retriever_calibrate.py`](#tooling-gen_dummy_kbpy-e-retriever_calibratepy)
- [Qualità del codice: lint, format, typing, test](#qualità-del-codice-lint-format-typing-test)
- [Linee guida di contributo](#linee-guida-di-contributo)

---

## Architettura in breve
- **Orchestratori** (CLI e UI) gestiscono l’esperienza utente e coordinano i moduli.
- **`pipeline/*`** fornisce utilità cross‑cutting (path, file I/O, logging, context, validazioni) e rimane privo di accessi di rete; forte **path‑safety**.
- **`semantic/*`** espone la façade `semantic.api` che coordina conversione PDF→MD, enrichment del frontmatter e indicizzazione.
- **Storage locale**: workspace per cliente in `output/timmy-kb-<slug>/{raw, book, semantic, config, logs}`.
- **DB SQLite**: Single Source of Truth (SSoT) per i tag in runtime (es. `semantic/tags.db`).

---

## Fasi operative e façade `semantic.api`
La façade `semantic.api` espone gli step principali:

1. **`convert_markdown(ctx, logger, slug)`**
   - Converte PDF in `raw/` in Markdown strutturato dentro `book/`.
   - Vedi policy nella sezione dedicata.

2. **`write_summary_and_readme(ctx, logger, slug)`**
   - Genera/aggiorna `SUMMARY.md` e `README.md` in `book/`.

3. **`load_reviewed_vocab(base_dir, logger)`**
   - Risolve i percorsi con `ensure_within_and_resolve` su `semantic/` e `tags.db`.
   - Se `tags.db` è assente: restituisce `{}` e registra un log informativo (enrichment disabilitato).
   - Lancia `ConfigError` solo per path non sicuri o DB illeggibile/corrotto (vedi sezione dedicata).

4. **`enrich_frontmatter(ctx, logger, vocab, slug)`**
   - Arricchisce il frontmatter dei Markdown con i metadati normalizzati.

5. **`index_markdown_to_db(ctx, logger, slug, scope, embeddings_client, db_path)`**
   - Estrae chunk testuali, calcola embedding, scrive su DB (idempotente) e ritorna KPI coerenti.

> **Fase `build_markdown_book`**: viene tracciata come singola fase che **copre l’intero blocco** `convert_markdown → write_summary_and_readme → load_reviewed_vocab → enrich_frontmatter`. Il “success” è emesso **solo a enrichment terminato**; gli `artifacts` riflettono i soli contenuti effettivi (esclusi `README.md`/`SUMMARY.md`).

---

## Regole di sicurezza I/O e path-safety
- **Guardie obbligatorie**: usare sempre `ensure_within` / `ensure_within_and_resolve` prima di accedere a file/dir derivati da input esterni o configurazioni.
- **Scritture atomiche**: impiegare `safe_write_text`/`safe_write_bytes` per evitare file parziali e condizioni di gara.
- **No side‑effects a import‑time**: i moduli non devono mutare `sys.path` né eseguire I/O quando importati.
- **Idempotenza**: tutti gli step devono poter essere ri‑eseguiti senza effetti collaterali (cleanup dei temporanei garantito anche in errore).

---

## Gestione errori, exit codes e osservabilità
- **Eccezioni tipizzate**: usare le exception di progetto (`ConfigError`, `PipelineError`, `ConversionError`, …) e includere **contesto**.
- **Contesto obbligatorio**: tutti i `PipelineError` (e derivate) devono includere `slug` e `file_path` quando rilevanti.
- **Orchestratori CLI**: catturano `ConfigError`/`PipelineError` e mappano su exit codes deterministici tramite `exit_code_for`. Nessun traceback non gestito.
- **ClientContext.load(require_env=True)**: se le ENV obbligatorie mancano o sono vuote, solleva immediatamente `ConfigError` con messaggio chiaro (mai `KeyError`).
- **Logging strutturato**: usare `phase_scope(logger, stage=..., customer=...)` per `phase_started/phase_completed/phase_failed` e valorizzare `artifacts` con numeri **reali**.

---

## Indicizzazione & KPI
- Inizializzazione schema DB: avviene una sola volta per run (all’avvio di `index_markdown_to_db`), evitando overhead per ogni file.
- Inserimenti: KPI basati sulle righe realmente inserite; idempotenza mantenuta (re-run ⇒ 0 nuove righe).

---

## CI
- Concurrency per ref/PR con `cancel-in-progress: true` per evitare job duplicati.
- Permissions minime (`contents: read`) se non servono scritture.
- Trigger `push`/`pull_request` limitati ai path rilevanti; schedule notturni invariati.

---

## Conversione Markdown: policy ufficiale
- Se **`raw/` non esiste** → `ConfigError` con `file_path`.
- Se **`raw/` non contiene PDF**:
  - **Non** chiamare il converter (evita segnaposto).
  - Se `book/` contiene già MD di contenuto → restituiscili.
  - Altrimenti → `ConfigError` (fail‑fast, con `file_path=raw/`).
- Se **ci sono PDF** in `raw/` → **invocare sempre** il converter.
- Gli `artifacts` conteggiano solo MD di contenuto (escludere `README.md`/`SUMMARY.md`).
- Categorie symlink: in presenza di categorie che sono link simbolici verso sottocartelle reali, i percorsi vengono
  risolti e verificati con path‑safety per evitare loop e mismatch; l’emissione del markdown procede senza eccezioni
  usando la base risolta per il calcolo dei percorsi relativi.

---

## Enrichment & vocabolario: comportamento fail‑fast
- SSoT runtime dei tag è sotto `semantic/` (tipicamente DB). L’**assenza** del DB → ok (nessun enrichment), restituisce `{}`.
- **Errori di path o I/O/DB** durante il load → **`ConfigError`** con `file_path` (fail‑fast, niente fallback silenziosi).
- L’enrichment avviene nella fase estesa `build_markdown_book`; una failure blocca il “success” della fase.

---

## Indexer & KPI DB (inserimenti reali)
- `insert_chunks(...)` ritorna il **numero effettivo** di righe inserite (idempotenza: re‑run ⇒ `0`).
- L’aggregato in `index_markdown_to_db(...)` usa la somma degli inserimenti reali per coerenti KPI/telemetria.

---

## UI: tab Finanza (I/O sicuro e cleanup)
- Scritture **solo** tramite `safe_write_bytes` con guardie `ensure_within`.
- Creazione del CSV temporaneo in `semantic/` con cleanup in **`finally`** (anche in caso d’errore).
- Niente fallback a `Path.write_bytes`.

---

## Tooling: `gen_dummy_kb.py` e `retriever_calibrate.py`
- **`gen_dummy_kb.py`**
  - Nessun side‑effect a import‑time; bootstrap delle dipendenze **lazy** in `_ensure_dependencies()`.
  - Supporta `--out <dir>` per generare un workspace esplicito; crea `raw/`, `book/`, `semantic/`, `config/`.
- **`retriever_calibrate.py`**
  - Evita append non atomici: accumula record in memoria e scrive una sola volta con `safe_write_text`.
  - Validazione destinazione dump con `ensure_within_and_resolve`.

---

## Qualità del codice: lint, format, typing, test
- **Formatter/Lint**: Black, isort, Ruff (config in `pyproject.toml`).
- **Typing**: mypy/pyright; preferire type hints espliciti, no `Any` se evitabile.
- **Test**: `pytest` con piramide unit → contract → smoke E2E; nessuna dipendenza di rete. Marcatori e `addopts` in `pytest.ini`.
- **Pre‑commit**: hook per lint/format/type e sicurezza (es. gitleaks); i commit devono passare tutti gli hook.

Esecuzione locale suggerita:
```bash
make install
make fmt && make lint && make type
make test
```

---

## Linee guida di contributo
1. **Modifiche minime e reversibili**: evitare refactor ampi senza necessità.
2. **Niente nuove dipendenze** senza forte motivazione e consenso.
3. **Aggiornare la documentazione** e il **CHANGELOG** per ogni modifica rilevante.
4. **Definition of Done**: lint/format/type/test verdi; nessuna regressione osservata nei workflow E2E; log strutturati coerenti.

> Per dubbi o proposte di evoluzione, apri una PR con descrizione completa (contesto, impatti, rischi, rollback) e riferimenti ai test/telemetria.
