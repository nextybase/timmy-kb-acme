# Changelog – Timmy-KB (Sintesi)

> Formato: **Keep a Changelog** e **SemVer**
> Nota: elenco condensato ai soli punti chiave che impattano UX, sicurezza, API pubbliche o qualità.

## [1.9.6] - 2025-09-27

### Added
- Utility `safe_append_text` in `pipeline.file_utils` per append atomici con path-safety, lock file e fsync opzionale.

### Fixed
- Calibrazione retriever: CLI `retriever_calibrate.py` ora usa `retrieve_candidates` validando scope/project e allineando i log strutturati.

### Changed
- Audit Vision (`semantic/vision_provision.py`) migra all'append sicuro, eliminando `open('a')` e preservando i JSON Lines.
- Strumenti CLI (`gen_dummy_kb.py`, `gen_vision_yaml.py`, `retriever_calibrate.py`) uniformati a logging `event` + `extra`.

### Docs
- Developer/Test/Coding Guide aggiornate con wrapper `retrieve_candidates`, guida di calibrazione e norme sul logging strutturato.

### Compatibility
- Nessun breaking change: gli strumenti esistenti restano compatibili.
- Migrazione consigliata: aggiorna gli script interni di audit/logging per usare `safe_append_text` e il pattern `logger.info("event", extra=...)`.

---

## [1.9.5] - 2025-09-26

### Added
- Vision onboarding in UI con pulsante esplicito **"Genera da Vision (AI)"**, progress a step e anteprima YAML prima dell'approvazione.
- Generazione contestuale di `semantic/cartelle_raw.yaml` e provisioning delle cartelle `docs/` solo dopo il click **"Approva e crea cartelle"**.
- Audit e idempotenza basati su `semantic/.vision_hash` con rigenerazione forzata opzionale (`force=True`).
- Vision Statement pipeline: `semantic/vision_ai.py` estrae il testo dal PDF, salva uno snapshot (`vision_statement.txt`) e genera `vision_statement.yaml` via `gpt-4.1-mini`.
- Script `py src/tools/gen_vision_yaml.py` carica `.env`, valida i percorsi del PDF e produce il mapping YAML con errori tipizzati (`ConfigError`).
- Test unitari `tests/test_vision_ai_module.py` per estrazione, conversione JSON->YAML e gestione `finish_reason="length"`.

### Changed
- `semantic/vision_ai.py` usa le chat completions con JSON Schema, salva il dump testuale e trasforma risposte vuote/rifiutate in `ConfigError`.
- `gen_vision_yaml.py` forza `ensure_dotenv_loaded()` prima di caricare il `ClientContext` e propaga exit code coerenti.

### Docs
- README, Architecture, Developer Guide e Test Suite aggiornati con la pipeline Vision e bump documentale a v1.9.5.
- Developer Guide e Guida UI aggiornate con il workflow Vision (upload → bottone → anteprima → approvazione).
- Coding Rules/Policy allineate: snapshot obbligatorio, uso di `safe_write_text` e path-safety sui PDF Vision.

---

## [1.9.4] - 2025-09-23

### Fixed
- Vocab loader: qualsiasi errore SQLite durante apertura/query/cursor è ora tipizzato come `ConfigError` con `file_path`.
- Conversione: caso “solo PDF non sicuri/symlink/fuori perimetro” solleva `ConfigError` con messaggio esplicito e hint operativo.
- Documenti: rimosso mojibake/encoding rotto in README e Developer Guide; correzioni ortografiche e terminologiche.

### Improvements
- Path-safety: conteggio e logging espliciti dei PDF scartati per path-safety/symlink.
- Retriever: documentata gestione embedding annidati/filtraggio vuoti nei KPI DB (nessun cambio API).

### Docs
- Developer Guide: sezioni aggiornate su fail-fast, path-safety, fase `build_markdown_book`, SQLite → `ConfigError`.
- User Guide/README: Troubleshooting con messaggio per “solo PDF non sicuri/fuori perimetro”.
- cSpell: configurazione ripulita (locale/overrides) e dizionario allineato alla terminologia.

### CI
- Preparata configurazione cSpell per uso in editor/CI (non-gating); nessun nuovo job obbligatorio.

---

## [Unreleased]

### UI
- Aggiunta verifica iniziale dello slug: il pulsante `Verifica cliente` controlla l'esistenza del workspace e instrada subito alla configurazione se già presente.
- Nuovo percorso per i clienti nuovi: upload del Vision Statement, creazione workspace, generazione immediata di `semantic/vision_statement.yaml` e `semantic/cartelle_raw.yaml`, editor inline con salvataggi atomici.
- Sidebar principale aggiornata: il bottone `Carica contesto` appare solo quando il workspace esiste; altrimenti un messaggio rimanda al bootstrap dalla landing.

### Fixed
- Conversione strutturata: gestione robusta delle categorie symlink in `convert_files_to_structured_markdown`
  (percorsi risolti in sicurezza, niente `ValueError` e nessun loop; ordinamenti invariati).
- Telemetria di fase: `build_markdown_book` copre anche `load_reviewed_vocab` e `enrich_frontmatter`; rimosso il “success” prematuro.
- Messaggi errore: tutti i `PipelineError` includono `slug` e `file_path` nei punti critici (validazioni/IO).
- KPI ingest DB: `kb_db.insert_chunks(...)` restituisce il numero **reale** di righe inserite (idempotenza: re-run ⇒ 0).

### Changed
- `semantic.convert_markdown(...)`: se `raw/` non ha PDF **non** invoca il converter; se ci sono PDF lo invoca sempre. `README.md`/`SUMMARY.md` esclusi dagli `artifacts`.
- `semantic_onboarding.py`: orchestratore con exit code deterministici (cattura `ConfigError`/`PipelineError`).
- UI Finanza (`src/ui/tabs/finance.py`): scritture solo tramite `safe_write_bytes` con guardie `ensure_within`; cleanup dei file temporanei spostato in `finally`.
- `semantic.vocab_loader`: comportamento **fail-fast** su path/DB non sicuri o illeggibili (alza `ConfigError` con `file_path`).

### Added
- Vision onboarding: pulsante esplicito, creazione di `semantic/cartelle_raw.yaml`, provisioning cartelle dal YAML e audit/idempotenza via `semantic/.vision_hash`.
- `src/tools/gen_dummy_kb.py`: supporto a `--out` per generare un workspace in una cartella esplicita; bootstrap lazy (nessun side-effect a import-time).
- `src/tools/retriever_calibrate.py`: dump JSONL atomico e validato (`ensure_within_and_resolve` + `safe_write_text`).
- Test anti-regressione:
  - `tests/test_convert_markdown_no_pdfs_raises.py`
  - `tests/test_semantic_onboarding_exitcodes.py`
  - `tests/test_finance_tab_io_safety.py`
  - `tests/test_vocab_loader_failfast.py`
  - `tests/test_gen_dummy_kb_import_safety.py`
  - `tests/test_retriever_calibrate_io.py`

### Docs
- Guide aggiornate: `docs/developer_guide.md` (flusso Vision) e `docs/guida_ui.md` (pulsanti/stati landing).
- `docs/developer_guide.md`: chiarita l’estensione della fase `build_markdown_book`; obbligo di `slug`/`file_path` nei `PipelineError`; KPI DB basati su inserimenti reali; note su `gen_dummy_kb --out`, fail-fast del vocabolario e hardening del tab Finanza.

---

## [Unreleased]
### Fixed
- Telemetria di fase: `build_markdown_book` include anche `load_reviewed_vocab` ed `enrich_frontmatter`; rimosso il “success” prematuro e conteggio `artifacts` dopo l’enrich.
- Errori contestualizzati: tutte le `PipelineError` in `pipeline.content_utils` includono `slug` e `file_path` nei casi “missing/not a directory” e validazioni affini.
- KPI ingest: `kb_db.insert_chunks(...)` restituisce il numero **reale** di righe inserite; aggregati coerenti in `index_markdown_to_db(...)` (idempotenza: re-run ⇒ 0).

### Changed
- `semantic.convert_markdown(...)`: se `raw/` **non** contiene PDF non invoca il converter (riusa gli MD esistenti o fallisce con `ConfigError`); se ci sono PDF esegue sempre la conversione. Esclude `README.md`/`SUMMARY.md` dagli `artifacts`.

### Added
- Test anti-regressione: `tests/test_convert_markdown_no_pdfs_raises.py` (RAW senza PDF ⇒ `ConfigError`; RAW senza PDF con MD preesistenti ⇒ ritorna MD esistenti).
- Test wrapping: `tests/test_semantic_api_errors.py` (firma converter errata ⇒ `ConversionError` con `slug`/`file_path`).
- Aggiornamenti smoke/path overrides: test che seedano `dummy.pdf` per rispettare la regola “converter solo con PDF”.

### Docs
- `docs/developer_guide.md`: chiarita estensione della fase `build_markdown_book`, obbligo di `slug`/`file_path` nelle `PipelineError`, KPI DB basati su inserimenti reali e comportamento ai re-run.

---

## [Unreleased]
### Fixed
- Telemetria di fase: `build_markdown_book` copre anche enrichment; rimosso “success” prematuro.
- Messaggi errore: `PipelineError` in `pipeline.content_utils` arricchite con `slug` e `file_path`.
- KPI ingest: `insert_chunks(...)` ritorna il numero **reale** di righe inserite; idempotenza rispettata (re-run → 0).
- Conversione Markdown: nessuno skip improprio in presenza di nuovi PDF; se `raw/` è vuoto si riusano i `.md` esistenti.

---

## [Unreleased]
### Fixed
- Telemetria di fase: `build_markdown_book` copre conversione **e** arricchimento; rimosso il “success” prematuro.
- Messaggi errore: tutte le `PipelineError` di `pipeline.content_utils` includono `slug` e `file_path` anche per “missing/not a directory”.
- KPI ingest: `insert_chunks(...)` ritorna il numero **reale** di righe inserite; idempotenza rispettata (secondo run → 0).

---

### Observability & Benchmarks (A1, B1, B2)
- **A1 (CI opzionale)**: workflow `bench.yml` (manuale + schedulato) che esegue `scripts/bench_embeddings_normalization.py` con output JSON e riassunto nel Job Summary. Non-gating; artifact pubblicato.
- **B1 (phase_scope)**: logging strutturato per fasi con campi `phase`, `status` (`start|success|failed`), `duration_ms`, `artifacts` (alias di `artifact_count`), `error` su failure. Back-compat mantenuta.
- **B2 (smoke osservabilità)**: test end-to-end per indexing e build book che verificano presenza/consistenza dei campi strutturati.

---

## [Unreleased]
### Fixed
- Markdown (content pipeline): intestazioni di categoria ora univoche anche per sottocartelle omonime allo stesso livello, usando una chiave basata sul percorso cumulativo (es. `2023/Q4` e `2024/Q4` emettono entrambe le "Q4").
 - Indexing/Retriever: esclusi `README.md` e `SUMMARY.md` dall’indicizzazione; filtrati e scartati embedding vuoti per singolo file (log "Embedding vuoti scartati").

## [2.0.0] - 2025-09-20
### Added
- Guardie esplicite per Google Drive negli orchestratori (`pre_onboarding`, `tag_onboarding`) e nella UI (`ui/services/drive_runner.py`).
- UI: caricamento `.env` idempotente per `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`.
- Supporto nativo extra `drive` in `pyproject.toml` (`pip install .[drive]`) e dipendenze base per `pip install .`.
- Test: aggiunti `tests/test_tag_onboarding_drive_guard_main.py` e `tests/test_ui_drive_services_guards.py`.

### Changed
- `src/tag_onboarding.py`: `_require_drive_utils()` invocato nel ramo `source=="drive"` prima di accedere al servizio.
- `src/ui/services/drive_runner.py`: guardie applicate nei servizi (`build_drive_from_mapping`, `emit_readmes_for_raw`, `download_raw_from_drive_with_progress`).
- `.github/workflows/import-smoke.yml`: reso non-gating (`continue-on-error: true`).

### Fixed
- Errori `TypeError` su funzioni Drive mancanti sostituiti con messaggi espliciti (ConfigError/RuntimeError con istruzioni installazione).

## [1.9.3] - 2025-09-20
### Added
- Embeddings: property/fuzz tests per `normalize_embeddings` e `cosine` (robustezza input edge).
- CI: workflow `import-smoke.yml` (anti side-effect a import-time) e check soft `scripts/ci/check_phase_artifacts.py`.
- Bench: summary S/M/L con delta% vs baseline opzionale; artifact JSON esteso.
- DB: test idempotenza `tests/test_kb_db_idempotency.py`.

### Changed
- Retriever: `cosine` numericamente stabile (rescaling, clamp [-1, 1]); skip candidati con embedding non valido.
- `pipeline/env_utils`: `_ensure_dotenv_loaded()` lazy; helpers `get_env_var/get_bool/get_int`.
- `semantic.api.index_markdown_to_db`: normalizzazione SSoT e validazioni esplicite (artifacts coerenti).
- `scripts/bench_embeddings_normalization.py`: classi S/M/L e misure per retriever+semantic.

### Fixed
- Path-safety DB: idempotenza insert su SQLite (no duplicati su re-run) con check applicativo.
- Lint/type: pulizia import/ignores; mypy 0 errori sui moduli core.

### Performance
- Indici DB: conferma `idx_chunks_project_scope` + indice UNIQUE “soft” su chiave naturale per prevenire duplicati futuri.

### CI
- Workflows bench/import-smoke non-gating; warnings informativi su `artifacts=0`.

---

## [1.9.2] — 2025-09-19
### Added
- **Content pipeline**: supporto ai PDF nel root di `raw/` con file aggregato in `book/`.
- **Test**: copertura per PDF in root, cleanup orfani, encoding `SUMMARY`, writer CSV hardened, loader vocab fail-closed.

### Changed
- `pipeline.content_utils`: cleanup idempotente dei `.md` in `book/`; `SUMMARY.md` con percent-encoding dei link.
- `semantic.auto_tagger.render_tags_csv`: firma con `*, base_dir`, path-safety forte (`ensure_within_and_resolve` + atomiche); call-site aggiornati.
- `semantic.vocab_loader`: **fail-closed** se manca `tags.db`; warning se DB vuoto; info con conteggio canonicals.

### Deprecated
- `semantic.tags_extractor.emit_tags_csv` in favore di `semantic.api.build_tags_csv(...)` o `auto_tagger.render_tags_csv(..., base_dir=...)`.

---

## [fix] — 2025-09-17
### Fixed
- `semantic/vocab_loader.py`: path-safety in **lettura** con `ensure_within_and_resolve`.

### Changed
- **Retriever**: `_default_candidate_limit()` come SSoT; `cosine(...)` iterator-safe.

### Tests
- Unitarie retriever (precedenze `candidate_limit`, casi edge) – **104 passed**.

---

## Smoke tests UI & E2E — 2025-09-17
### Added
- `scripts/smoke_streamlit_finance.py` (tab **Finanza**) e `scripts/smoke_e2e.py` (E2E headless con push GitHub disabilitato).

### Changed
- UI Finanza: bottone “Importa in finance.db” sempre attivo con gating nell’handler (stabilità test).

---

## [1.10.0] — 2025-09-13
> Nota: versione maggiore rilasciata prima di 1.9.x; l’ordinamento qui è cronologico.

### Added
- **Retriever**: metriche leggere (embed/fetch/score/total ms) + tool `retriever_calibrate.py`.
- **UI**: sidebar “Ricerca (retriever)” con `candidate_limit` e `latency_budget_ms` persistiti in `config.yaml`.

### Changed
- **Path-safety letture** in `tag_onboarding.py` (hash) e cleanup import.

### Removed / Breaking
- **Fallback semantici** in `semantic.api` (README/SUMMARY/convert): ora **fail-fast**.
- **Drive adapter**: import hard delle dipendenze (errore esplicito se assenti).

---

## [fix] — 2025-09-14
### Changed
- `onboarding_ui.py`: nessun side-effect a import-time; tipizzazione e subprocess via `sys.executable`.

### Security
- `finance.api.import_csv`: path-safety `open_for_read(...)` (traversal mitigato).

---

## [1.8.2] — 2025-09-07
### Added
- `pipeline/path_utils.ensure_within_and_resolve` (SSoT letture sicure) + test traversal/symlink.

### Changed
- Tutte le **letture** in `semantic/*` e `pipeline/*` passano per il wrapper.

---

## [1.8.1] — 2025-09-06
### Added
- Suite test semantica (estrazione, mapping, frontmatter, summary/readme, E2E enrichment).

### Changed
- SSoT contratti: uso `semantic.types.ClientContextProtocol`; SRP e refactor `content_utils`/estrattori.

---

## [1.8.0] — 2025-09-06
### Breaking
- **Formato YAML** unificato; façade `semantic.api` unica; rimosso `semantic_onboarding.py`.

### Added
- `to_kebab()` (SSoT normalizzazione), CLI `src/semantic_headless.py`.

### Changed
- Tipizzazione/ottimizzazioni estrazione semantica; logging ASCII-only; refactor UI/runner.

### Security
- Path-safety e scritture atomiche estese (writer README/SUMMARY/MD).

---

## [1.7.0] — 2025-09-01
### Added
- cSpell e script `scripts/fix_mojibake.py`; normalizzazione tipografica docs.

### Changed
- Editor mapping → tab **Configurazione**; struttura `raw/` derivata da `tags_reviewed.yaml`.

---

## [1.6.1] — 2025-08-30
### Added
- Task **CILite**; mypy mirato su `ui`.

### Fixed
- Flake8 a 0; pytest verde su unit + `content_utils`; pulizia import.

---

## [1.6.0] — 2025-08-29 — Interfaccia Streamlit
### Added
- **UI Streamlit** con tab **Configurazione / Drive / Semantica**; runner Drive; chiusura controllata.

### Changed
- Gating UI (slug/nome); caching stato; preview docker gestita; messaggistica chiara.

### Security
- Path-safety forte e scritture atomiche in UI/runner.

---

## [1.5.0] — 2025-08-27
### Added
- Suite test PyTest (unit/contract/smoke) + `pytest.ini`; doc test dedicata.

### Changed
- Logging strutturato SSoT; orchestratori snelliti; push GitHub hardening (retry/lease/redazione).

### Security
- Path-safety `ensure_within` e scritture atomiche su pipeline core.

---

## [1.4.0] — 2025-08-26
### Added
- Preview HonKit/GitBook via Docker; adapter Preview; IO sicure; CI (Qodana/GitHub Actions).

### Changed
- Pipeline contenuti: conversione gerarchica, fingerprint, generatori SUMMARY/README atomici.

### Security
- Rimozione rischi traversal su write/delete; autenticazione GitHub sicura.

---

## [1.3.0] — 2025-08-26
### Changed
- Refactor orchestratori secondo linee guida (funzioni pure testabili; SRP in CSV/enrichment).

### Documentation
- Aggiornate Architecture/Developer/Coding Rules.

---

## [1.2.x] — 2025-08-24/25
### Added
- Nuovi orchestratori (poi deprecati); adapter fallback/preview; utility file (atomiche, path-safety); indice `docs/SUMMARY.md`.

### Changed
- Centralizzazione redazione log e path-safety; tool dummy rigenerato; test dummy/CI di base.

---

## [1.1.0] — 2025-08-23 — Baseline stabile
### Added
- Struttura modulare `src/pipeline/*`; orchestratori `pre_onboarding`, `tag_onboarding`, `onboarding_full`.

### Changed

## 1.9.3 — 2025-09-23

Fix
- ENV hardening: nessun KeyError propagato; ConfigError con messaggi chiari e orchestratori con exit code deterministici.
- Vocabolario: assenza semantic/tags.db -> {} con log informativo; errori solo per path non sicuri o DB illeggibile.
- Listing PDF: validazione per-file e skip sicuro di symlink/traversal con warning strutturati; conversione fallisce se restano solo README.md/SUMMARY.md.

Improvements
- Indexer: schema inizializzato una sola volta per run; rimosso overhead nei loop mantenendo idempotenza e KPI basati su inserimenti reali.
- Orchestratori: tag_onboarding_main snellito in helper privati (download/copy, CSV, checkpoint, stub) senza modifiche di API/UX.

Docs
- Developer Guide aggiornato: policy “assenza DB ⇒ {}” per il vocabolario; path-safety per-file sui PDF; nota su initializzazione schema Indexer.

CI
- E2E/CI/import-smoke/bench: abilitata concurrency per ref/PR; permissions minime (contents: read); trigger push/pull_request limitati ai path rilevanti; schedule notturni invariati.

Note
- Nessun breaking change.


- Output standard: `output/timmy-kb-<slug>/` (raw, book, semantic, config, logs); documentazione completa iniziale.
