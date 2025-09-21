# Changelog – Timmy-KB (Sintesi)

> Formato: **Keep a Changelog** e **SemVer**
> Nota: elenco condensato ai soli punti chiave che impattano UX, sicurezza, API pubbliche o qualità.

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
- Output standard: `output/timmy-kb-<slug>/` (raw, book, semantic, config, logs); documentazione completa iniziale.
