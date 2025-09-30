# Suite di test

Questa guida riflette l'assetto reale della suite Pytest del repo, raggruppa i file per categoria e indica marker/flag utili. Vale per esecuzione locale e per CI.

---

## Come eseguire

```powershell
# dal venv attivo
make test           # esegue la suite locale
make test-vscode    # variante per VS Code

# oppure direttamente
pytest -ra          # tutto tranne i test esclusi tramite marker in pytest.ini
pytest -ra -m "push"   # include test che richiedono push su GitHub
pytest -ra -m "drive"  # include test che richiedono Google Drive
pytest -ra -m "slow"   # include smoke/end-to-end lenti
```

**Default:** in CI conviene mantenere l'esclusione di `push` e `drive`.

---

## Categorie e file

> L'elenco e completo per macro-categorie e cita i file chiave realmente presenti in `tests/`. Alcuni casi sono *skipped* su Windows (symlink) o richiedono extra opzionali.

**Windows — extra opzionali consigliati:** per eseguire anche i test normalmente *skipped* su Win, abilita i symlink (Impostazioni -> Modalita sviluppatore oppure prompt Administrator con privilegio `SeCreateSymbolicLinkPrivilege`), abilita i *long paths* (Criteri di gruppo/Registro `LongPathsEnabled=1` e, se usi Git, `git config --system core.longpaths true`), e installa i pacchetti opzionali come `PyMuPDF` per i test Vision AI e l'extra Drive (`pip install .[drive]`) per i test con Google Drive. Senza questi extra, i test restano *skipped* e la suite passa comunque.

### 1) Unit — Core utility, path-safety, YAML e stringhe
*Obiettivo:* verifiche atomiche su path-safety, IO e helper di base.

- **Path & FS safety:** `test_architecture_paths.py`, `test_path_utils.py`, `test_path_safety_reads.py`, `test_content_utils.py`, `test_content_utils_slug_traversal_error.py`, `test_content_utils_symlink_category.py` (*skip su Win*), `test_pdf_iteration_symlink.py` (*skip su Win*).
- **IO atomico:** `test_file_io_append.py`, `test_yaml_utils.py`.
- **YAML validation:** `test_yaml_validation.py`.
- **String/slug:** `test_slug_property.py`.

### 2) Semantic API — Conversione, frontmatter, book, listing, indicizzazione, tag CSV
*Obiettivo:* garantire corretto flusso di conversione e arricchimento, generazione libro e indicizzazione.

- **Conversione & guardie:** `test_semantic_api_convert_md.py`, `test_semantic_convert_failfast.py`, `test_convert_markdown_no_pdfs_raises.py`, `test_convert_markdown_rerun_processes_new_pdfs.py`, `test_convert_markdown_unsafe_message.py`.
- **Frontmatter & arricchimento:** `test_semantic_api_frontmatter.py`, `test_semantic_api_enrich_frontmatter.py`, `test_semantic_enrich_ctx_override.py`, `test_semantic_enrich_and_unicode.py`, `test_semantic_frontmatter_and_matching.py`, `test_semantic_headless_enrichment_without_vocab.py`.
- **Build libro (SUMMARY/README) & listing:** `test_semantic_build_markdown_book.py`, `test_semantic_api_summary_readme.py`, `test_semantic_api_list_content_markdown.py`.
- **Estrattore & mapping:** `test_semantic_extractor.py`, `test_semantic_extractor_punct_matching.py`, `test_semantic_mapping.py`.
- **Indicizzazione DB:** `test_semantic_index_markdown_db.py`.
- **Tag CSV:** `test_semantic_tags_csv.py`, `test_unit_build_tags_csv.py`.
- **Error handling:** `test_semantic_api_errors.py`, `test_semantic_onboarding_exitcodes.py`.

### 3) Vision AI — Generazione mapping da PDF e provisioning
*Obiettivo:* verificare pipeline Vision e sicurezza dei percorsi.

- **Vision pipeline (PyMuPDF richiesto):** `test_vision_ai.py`, `test_vision_ai_module.py` (*skipped se PyMuPDF assente*).
- **Provisioning da Vision:** `test_vision_provision.py`.
- **Path-safety Vision:** `test_semantic_vision_path_safety.py`.

### 4) Orchestratori e CLI — Onboarding e flussi operativi
*Obiettivo:* smoke end-to-end e contratti dei flussi CLI.

- **Smoke end-to-end (`slow`):** `tests/test_smoke_e2e.py`, `tests/test_smoke_dummy_e2e.py`. Nota: orchestrano l'intero onboarding (pre/tag/semantic), richiedono `reportlab` per la generazione PDF e invocano la CLI.
- **Orchestratori/tag onboarding:** `test_tag_onboarding_cli_smoke.py`, `test_tag_onboarding_helpers.py`, `test_onboarding_full_paths.py`.
- **CLI & exit-codes:** `test_cli_env_missing.py`, `test_cli_gen_vision_yaml.py`, `test_contract_defaults.py`, `test_contract_artifacts.py`.
- **NLP -> DB:** `test_run_nlp_to_db.py`.

### 4bis) Tag review e provisioning — Pipeline tag e provisioning
*Obiettivo:* verifiche su writer, validazione e provisioning dei tag.

- **Auto-tagger writer (CSV render):** `tests/test_auto_tagger_writer.py`.
- **Provisioning da YAML (directories):** `tests/test_provision_from_yaml.py`.
- **Book purity adapter (guardie path):** `tests/test_book_purity_adapter.py`.
- **Validator unit (validazione tags):** `tests/test_unit_tags_validator.py`.
- **Reviewed paths (validazione/guardie):** `tests/test_validate_tags_reviewed_paths.py`.

### 5) UI (Streamlit) — Onboarding workspace e azioni
*Obiettivo:* mantenere consistenza dei path, salvataggio YAML e controlli di servizio.

- **Landing/paths:** `test_ui_paths_box.py`, `test_ui_labels.py`.
- **Inizializzazione/rigenerazione:** `test_ui_regenerate_yaml.py`, `test_ui_save_both_yaml.py`, `test_ui_save_both_yaml_negative.py`.
- **Vision gating e debug:** `test_ui_vision_gating.py`, `test_ui_debug_expander.py`.
- **Drive services guards:** `test_ui_drive_services_guards.py`.
- **Utilita:** `test_ui_utils.py`.

### 6) Retriever — Parametri, scoring, top-K, configurazione
*Obiettivo:* validazioni API, configurazione e qualita del ranking.

- **API & validazioni:** `test_retriever_api.py`, `test_retriever_validate.py`.
- **Config & auto-budget:** `test_retriever_config.py`, `test_retriever_unit.py`.
- **Scoring & ranking:** `test_retriever_scoring.py`, `test_retriever_topk.py`.
- **Strumenti IO:** `test_retriever_calibrate_io.py`.
- **Proprieta embedding (Hypothesis/cosine):** `test_embeddings_property.py`.

### 7) DB layer e ingest — SQLite, idempotenza, performance
*Obiettivo:* correttezza schema, idempotenza e ingest sicura.

- **Schema & init:** `test_indexer_init_failfast.py`, `test_indexer_schema_once.py`.
- **Inserimento & idempotenza:** `test_kb_db_insert.py`, `test_kb_db_idempotency.py`, `test_kb_db_path_safety.py`, `test_db_safety.py`.
- **Ingest:** `test_ingest_performance.py`, `test_ingest_safety.py`.

### 8) Environment e import safety — Config, lazy load, dipendenze
*Obiettivo:* robustezza del caricamento config e sicurezza degli import.

- **ENV & dotenv:** `test_env_loader.py`, `test_env_lazy.py`.
- **Import safety:** `test_gen_dummy_kb_import_safety.py`, `test_imports.py`.
- **Landing & override percorsi:** `test_landing_slug_paths.py`, `test_path_overrides_extended.py`.

### 9) Osservabilita e logging — Phase scope, smoke
*Obiettivo:* coerenza dei log strutturati e degli eventi di fase.

- **PhaseScope:** `test_phase_scope.py`, `test_phase_scope_structured.py`.
- **Convert phases & logging:** `test_semantic_convert_phase_scope.py`, `test_context_logging_events.py`.
- **Observability smoke:** `test_observability_smoke.py`.
- **Coder logging:** `test_timmy_kb_coder_logging.py`.

### 10) Prompting e layout — Prompt builder, suggerimenti layout
*Obiettivo:* corretto rendering di prompt e suggerimenti layout.

- **Prompt builder:** `test_prompt_builder.py`.
- **Layout enricher:** `test_layout_enricher.py`.

### 11) Adapter e IO esterni — Drive, finanza, ecc.
*Obiettivo:* integrare servizi esterni garantendo fallback e guardie.

- **Drive:** `test_drive_guards.py`, `test_drive_runner_pagination.py`, `test_drive_runner_progress.py`, `test_tag_onboarding_drive_guard_main.py`.
- **Finance tab (IO safety):** `test_finance_tab_io_safety.py`.
- **Client OpenAI (fallback/config):** `test_client_factory.py`.

### 12) Vocab e loader — SQLite vocab, fallback e fail-fast
*Obiettivo:* corretta gestione di vocab e fallimenti attesi.

- **Vocab loader:** `test_vocab_loader.py`, `test_vocab_loader_failfast.py`, `test_vocab_loader_sqlite_errors.py`.
- **Integrazione DB:** `tests/test_vocab_loader_integration_db.py`.

### 13) Script e qualita repo
*Obiettivo:* mantenere la qualita del contenuto del repo.

- **Sanitizzazione file:** `scripts/test_forbid_control_chars.py`.

---

## Marker e convenzioni

- `slow` — test lenti/smoke end-to-end.
- `push` — richiedono `GITHUB_TOKEN`/rete.
- `drive` — richiedono credenziali/permessi Google Drive (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`).
- **Logging strutturato:** evento + `extra` con `slug`, `file_path`, `scope` dove applicabile.
- **Path safety:** tutte le operazioni file-system passano per `ensure_within_and_resolve` + scritture atomiche (`safe_write_text/bytes`).

---

## Esecuzione mirata

```powershell
# singolo file
pytest tests/test_semantic_index_markdown_db.py -ra
# singolo test
pytest tests/test_semantic_api_summary_readme.py::test_write_summary_and_readme_generators_fail_raise -ra
# filtro per substring
pytest -k "embedding_pruned" -ra
```

---

## Note e manutenzione

- **Aggiornamento documentazione:** mantenere questa pagina allineata quando si aggiungono/cambiano test (nuovi moduli semantic/UI/retriever).
- **Tag review e provisioning:** non sono marcati `slow` ma richiedono fixture workspace/dummy (es. `dummy_kb`).
