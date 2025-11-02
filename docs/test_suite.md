# Test Suite — v1.0 Beta

Guida ufficiale alla suite **Pytest** del progetto. Allineata a: logging centralizzato con redazione, dipendenze SSoT (pip-tools), UI import-safe, **stub Streamlit centralizzati** e **helper symlink unificato**. Nessun riferimento a legacy o migrazioni.

---

## Come eseguire

```bash
# dal venv attivo
make test            # esegue l'intera suite locale
make test-vscode     # variante comoda per VS Code

# direttamente con pytest
pytest -ra                   # esegue la suite rispettando i marker di default
pytest -ra -m "push"         # include test che richiedono GitHub
pytest -ra -m "drive"        # include test che richiedono Google Drive
pytest -ra -m "slow"         # include smoke / end-to-end lenti
pytest -ra -m "contract"     # verifica i contratti UI/gating
pytest -ra -m "e2e"          # attiva gli end-to-end Playwright (browser)
```
> Nota: i test `e2e` richiedono le dipendenze extra (`pip install -r requirements-dev.txt`) e l'installazione del browser con `playwright install chromium`.
**Default CI:** i test marcati `push`, `drive` e `e2e` sono esclusi per impostazione predefinita.

> 📦 **Dipendenze opzionali**: alcuni test UI (es. `tests/ui/test_preview_stub.py`) importano YAML tramite `pyyaml`. Se esegui in modo mirato singoli file, assicurati di avere `pyyaml` installato (lo ottieni automaticamente con `pip install -r requirements-dev.txt`).

---

## Marker e convenzioni

- `slow` — test lenti/smoke end-to-end.
- `push` — richiedono `GITHUB_TOKEN`/rete.
- `drive` — richiedono `SERVICE_ACCOUNT_FILE`/`DRIVE_ID`.
- `contract` — snapshot contrattuali dell'interfaccia (navigazione/gate).
- `e2e` — test end-to-end con Streamlit + Playwright.
- **Logging strutturato:** usa sempre `get_structured_logger(...)`; gli `extra` devono includere i campi utili (es. `slug`, `file_path`, `scope`).
- **Path-safety & I/O atomico:** ogni accesso passa da helper della pipeline (`ensure_within_and_resolve`, `safe_write_text/bytes`).

---

## Categorie e file principali

> L’elenco riassume i file presenti in `tests/`. Alcuni casi vengono *skippati* su Windows (symlink) o richiedono extra opzionali.

### 1) Unit — Core utility, path-safety, YAML e stringhe
- **Path & FS safety:** `test_architecture_paths.py`, `test_path_utils.py`, `test_path_safety_reads.py`, `test_content_utils.py`, `test_content_utils_slug_traversal_error.py`, `test_content_utils_symlink_category.py` (*skip Win*), `test_pdf_iteration_symlink.py` (*skip Win*).
- **I/O atomico & YAML:** `test_file_io_append.py`, `test_yaml_utils.py`, `test_yaml_validation.py`.
- **String/slug:** `test_slug_property.py`.

### 2) Semantic API — Conversione, frontmatter, book, indicizzazione, tag CSV
- **Conversione & guardie:** `test_semantic_api_convert_md.py`, `test_semantic_convert_failfast.py`, `test_convert_markdown_no_pdfs_raises.py`, `test_convert_markdown_rerun_processes_new_pdfs.py`, `test_convert_markdown_unsafe_message.py`.
- **Frontmatter & arricchimento:** `test_semantic_api_frontmatter.py`, `test_semantic_api_enrich_frontmatter.py`, `test_semantic_enrich_ctx_override.py`, `test_semantic_enrich_and_unicode.py`, `test_semantic_frontmatter_and_matching.py`, `test_semantic_headless_enrichment_without_vocab.py`.
- **Build libro & listing:** `test_semantic_build_markdown_book.py`, `test_semantic_api_summary_readme.py`, `test_semantic_api_list_content_markdown.py`.
- **Estrattore & mapping:** `test_semantic_extractor.py`, `test_semantic_extractor_punct_matching.py`, `test_semantic_mapping.py`.
- **Indicizzazione DB:** `test_semantic_index_markdown_db.py`.
- **Tag CSV:** `test_semantic_tags_csv.py`, `test_unit_build_tags_csv.py`.
- **Error handling & exit-code:** `test_semantic_api_errors.py`, `test_semantic_onboarding_exitcodes.py`.

### 3) Vision AI — Mapping da PDF e provisioning
- **Vision pipeline (PyMuPDF opzionale):** `test_vision_ai.py`, `test_vision_ai_module.py` (*skipped se PyMuPDF assente*).
- **Provisioning da Vision:** `test_vision_provision.py`.
- **Path-safety Vision:** `test_semantic_vision_path_safety.py`.

### 4) Orchestratori e CLI — Onboarding e flussi operativi
- **Smoke end-to-end (`slow`):** `tests/test_smoke_e2e.py`, `tests/test_smoke_dummy_e2e.py`.
- **Orchestratori & tag onboarding:** `test_tag_onboarding_cli_smoke.py`, `test_tag_onboarding_helpers.py`, `test_onboarding_full_paths.py`.
- **CLI & contratti/exit-codes:** `test_cli_env_missing.py`, `test_cli_gen_vision_yaml.py`, `test_contract_defaults.py`, `test_contract_artifacts.py`.
- **NLP → DB:** `test_run_nlp_to_db.py`.

### 4bis) Tag review e provisioning
- **Writer CSV:** `tests/test_auto_tagger_writer.py`.
- **Provisioning YAML → directories:** `tests/test_provision_from_yaml.py`.
- **Book purity adapter (guardie path):** `tests/test_book_purity_adapter.py`.
- **Validator unit (tag):** `tests/test_unit_tags_validator.py`.
- **Reviewed paths:** `tests/test_validate_tags_reviewed_paths.py`.

### 5) UI (Streamlit) - Onboarding workspace e azioni
- **Landing/paths:** `tests/test_ui_paths_box.py`, `tests/test_ui_labels.py`.
- **Inizializzazione/rigenerazione:** `tests/test_ui_regenerate_yaml.py`, `tests/test_ui_save_both_yaml.py`, `tests/test_ui_save_both_yaml_negative.py`.
- **Vision gating/debug:** `tests/test_ui_vision_gating.py`, `tests/test_ui_debug_expander.py`.
- **Drive services guards:** `tests/test_ui_drive_services_guards.py`.
- **Preview gating:** `tests/test_ui_preview_gating.py`.
- **Utilità:** `tests/test_ui_utils.py`.

> Gli stub Streamlit sono centralizzati in `tests/ui/streamlit_stub.py` e riusati nei test UI.

### 6) Retriever — Parametri, scoring, top-K, configurazione
- **API & validazioni:** `test_retriever_api.py`, `test_retriever_validate.py`.
- **Config & auto-budget:** `test_retriever_config.py`, `test_retriever_unit.py`.
- **Scoring & ranking:** `test_retriever_scoring.py`, `test_retriever_topk.py`.
- **Strumenti I/O:** `test_retriever_calibrate_io.py`.
- **Proprietà embedding:** `test_embeddings_property.py`.

### 7) DB layer e ingest — SQLite, idempotenza, performance
- **Schema & init:** `test_indexer_init_failfast.py`, `test_indexer_schema_once.py`.
- **Inserimento & idempotenza:** `test_kb_db_insert.py`, `test_kb_db_idempotency.py`, `test_kb_db_path_safety.py`, `test_db_safety.py`.
- **Ingest:** `test_ingest_performance.py`, `test_ingest_safety.py`.

### 8) Environment e import-safety — Config, lazy load, dipendenze
- **ENV & dotenv:** `test_env_loader.py`, `test_env_lazy.py`.
- **Import-safety:** `test_gen_dummy_kb_import_safety.py`, `test_imports.py`, `test_preflight_import_safety.py`.
- **Landing & override percorsi:** `test_landing_slug_paths.py`, `test_path_overrides_extended.py`.

### 9) Osservabilità e logging — Phase scope, redazione, smoke
- **PhaseScope:** `test_phase_scope.py`, `test_phase_scope_structured.py`.
- **Convert phases & logging:** `test_semantic_convert_phase_scope.py`, `test_context_logging_events.py`.
- **Redazione log:** `tests/test_logging_redaction.py`.
- **Observability smoke:** `test_observability_smoke.py`.
- **Coder logging:** `test_timmy_kb_coder_logging.py`.

### 10) Prompting e layout — Prompt builder, suggerimenti
- **Prompt builder:** `test_prompt_builder.py`.
- **Layout enricher:** `test_layout_enricher.py` (+ eventuale variante parametrizzata).

### 11) Adapter e IO esterni — Drive, finanza, client
- **Drive:** `test_drive_guards.py`, `test_drive_runner_pagination.py`, `test_drive_runner_progress.py`, `test_tag_onboarding_drive_guard_main.py`.
- **Finance tab (IO safety):** `test_finance_tab_io_safety.py`.
- **Client OpenAI (fallback/config):** `test_client_factory.py`.

### 12) Vocab e loader — SQLite, fallback e fail-fast
- **Vocab loader:** `test_vocab_loader.py`, `test_vocab_loader_failfast.py`, `test_vocab_loader_sqlite_errors.py`.
- **Integrazione DB:** `tests/test_vocab_loader_integration_db.py`.

### 13) Script e qualità repo
- **Sanitizzazione file (test):** `tests/scripts/test_forbid_control_chars.py`.
- **Script CLI correlato:** `scripts/forbid_control_chars.py`.

### 14) Process utils — Esecuzione comandi esterni
- **Redazione tail stdout/stderr:** `tests/test_proc_run_cmd_redacts_output.py`.

### 15) UI end-to-end (Playwright)
- **Abilita + Preview (marker `e2e`):** `tests/e2e/test_enable_and_preview.py` (Streamlit headless, stub tags/preview). Requisiti: `pip install -r requirements-dev.txt`, `playwright install chromium`.

---

## Script di supporto (`scripts/`)

Strumenti CLI che fungono da estensioni e smoke manuali della suite:
- **Smoke E2E rapidi:** `scripts/smoke_e2e.py`, `scripts/e2e_smoke_test.py`.
- **Gating Semantica:** `tools/smoke_semantics_gating.py` (verifica che la pagina Semantica compaia solo con PDF in `raw/`).
- **Benchmark retriever/semantic:** `scripts/bench_embeddings_normalization.py` (output opzionale in JSON).
- **SBOM:** `scripts/sbom.sh` (genera `sbom.json`).
- **Migrazioni operative:** `scripts/migrate_yaml_to_db.py` (conversioni YAML → SQLite per i tag).

> Quando si introduce un nuovo script CLI: riusare helper di path-safety e writer atomici (`pipeline.*`), documentare le variabili d’ambiente e valutare un test dedicato.

---

## Linee guida per nuovi test

- Usa le fixture `dummy_workspace`, `dummy_ctx`, `dummy_logger` per isolare i percorsi cliente.
- Mantieni coerente lo slug (`dummy` per i workspace di test).
- Evita path hard-coded; usa quelli restituiti dalle fixture.
- Per test che richiedono assistente/segreti: usa marker dedicati e `skipif`; preferisci mock/fake client (OpenAI/Vision/Drive).
- Se devi asserire log strutturati, usa `get_structured_logger` e verifica i campi `extra` rilevanti.
- Non eseguire I/O a import-time nei moduli sotto test (import-safety).

---

## Esecuzione mirata

```bash
# singolo file
pytest tests/test_semantic_index_markdown_db.py -ra
# singolo test
pytest tests/test_semantic_api_summary_readme.py::test_write_summary_and_readme_generators_fail_raise -ra
# filtro per substring
pytest -k "embedding_pruned" -ra
# contratti UI
pytest -m "contract" -ra
# end-to-end Playwright
pytest -m "e2e" -ra
```

---
## Pre-commit — configurazione & comandi rapidi

**Perché**: manteniamo qualità e sicurezza *prima* del push. Gli hook girano su due stadi:
- `pre-commit`: formattazione, linting, controlli di base (file/UTF-8, policy UI, ingest).
- `pre-push`: check più “pesanti” (typing selettivo, QA degradabile).

**Installazione**
```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

**Hook principali (sintesi)**
- *Format/Lint* (**commit + push**): `isort` → `black` → `ruff --fix`.
- *Typing* (**push**): `mypy` su UI config & driver Drive.
- *Safety I/O & API*: `forbid-unsafe-file-reads`, `no-dup-ingest-csv`.
- *Unicode/UTF-8*: `fix-control-chars` (fix) + `forbid-control-chars` (guard).
- *UI policy*: `forbid-streamlit-deprecated`, `ui-beta0-compliance`.
- *Boundary error*: `forbid-legacy-valueerror` (vietato `raise ValueError(` in runtime).
- *Security/Docs* (**commit**): `gitleaks` (segreti), `cspell` (README+docs).
- *Doc governance* (**commit**): `agents-matrix-check` — verifica che la matrice in `docs/AGENTS_INDEX.md` sia **allineata** agli `AGENTS.md` locali; fallisce se va rigenerata. Esegue `python scripts/gen_agents_matrix.py --check`; scope file: `docs/AGENTS_INDEX.md`, `src/**/AGENTS.md`, `tests/AGENTS.md`, `.codex/AGENTS.md`, `AGENTS.md`.

**Esecuzioni tipiche**
```bash
# tutto lo stadio commit su tutti i file
pre-commit run --all-files

# simulare lo stadio push (utile in locale)
pre-commit run --hook-stage pre-push --all-files

# un singolo hook su tutti i file
pre-commit run ruff --all-files
pre-commit run agents-matrix-check --all-files

# fixer/guard Unicode/UTF-8
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files

# solo alcuni percorsi
pre-commit run --files src/pipeline/file_utils.py tests/test_semantic_index_markdown_db.py

# mostrare diff alla failure
pre-commit run -a --show-diff-on-failure

# (avanzato) saltare temporaneamente uno o più hook durante il commit
SKIP=ruff,black git commit -m "…"
```

**Dettagli di configurazione**
- Versione minima: `pre-commit ≥ 3.6`; Python di default: `3.11`.
- Esclusi dal scan: `.venv/`, `node_modules/`, `output/`, `dist/`, `build/`, `docs/_build/`.
- Scope file: Python limitato a `src|tests`; cSpell = `README.md` e `docs/*.md`.
- Matrice AGENTS: hook locale `agents-matrix-check` (`.pre-commit-config.yaml` → `repo: local`, `id: agents-matrix-check`, `entry: python scripts/gen_agents_matrix.py --check`, `language: system`, `pass_filenames: false`, `files: ^docs/AGENTS_INDEX\.md$|^src/.*/AGENTS\.md$|^tests/AGENTS\.md$|^\.codex/AGENTS\.md$|^AGENTS\.md$`).

> Riferimenti: `.pre-commit-config.yaml` (stadi, scope, hook e argomenti), README/Developer Guide (installazione rapida), User Guide (fixer/guard Unicode).


---

## Settings & guard segreti

- Test mirati: `pytest -m "settings or pipeline or ui or semantic" --maxfail=1` verifica il caricamento `Settings`, l'esposizione in `ClientContext` e i consumer UI/Semantic che dipendono dal wrapper.
- Hook anti-segreti: `pre-commit run no-secrets-in-yaml --all-files` (anche in CI) assicura che `config/*.ya?ml` contengano solo riferimenti `_env`.
- Smoke pagina Streamlit: dopo un cambio alle configurazioni avvia `streamlit run onboarding_ui.py` e verifica la scheda **Tools -> Secrets Health Check** (nessun valore viene visualizzato).
- Riferimenti: [Configurazione (.env vs config)](configuration.md) e ADR [0002-separation-secrets-config](adr/0002-separation-secrets-config.md).

---

## Note

- Mantieni questa pagina allineata quando si aggiungono o cambiano i test.
- I test marcati `slow` orchestrano onboarding end-to-end; i test Drive/GitHub richiedono variabili configurate o restano esclusi di default.
