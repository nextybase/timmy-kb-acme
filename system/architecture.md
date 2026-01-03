# Architettura del repository (pre-Beta / work in progress)

Questo documento offre una mappa strutturale del repository con un focus descrittivo: `src/` è il core applicativo, tutto il resto è supporto, runtime o locale.

La sezione “Repository Root” elenca ogni elemento a profondità 1 con ruolo/uso. La sezione “src/ — Core Architecture” descrive le aree del codice e le sotto-aree (profondità 2) usando esclusivamente l’inventario fornito.

Stato corrente: pre-Beta; inventario e classificazioni sono work in progress.


## Repository Root

### Directory (depth 1)

- `.codex/` — policy e workflow Codex (support).
- `.git/` — metadati Git (support).
- `.git.bak/` — backup Git (locale; da verificare).
- `.github/` — automazioni GitHub (support).
- `.hypothesis/` — cache Hypothesis (locale; cache).
- `.mypy_cache/` — cache mypy (locale; cache).
- `.pytest_cache/` — cache pytest (locale; cache).
- `.pytest_clients_db/` — artefatti pytest (locale; da verificare).
- `.qodana/` — cache/artefatti Qodana (locale; cache).
- `.ruff_cache/` — cache Ruff (locale; cache).
- `.timmy_kb/` — artefatti Timmy KB (locale; runtime).
- `.venv/` — virtualenv locale (locale; rigenerabile).
- `.vscode/` — configurazione editor (support).
- `__pycache__/` — bytecode Python (locale; cache).
- `build/` — output di build (locale; runtime).
- `clients_db/` — dati clienti (runtime; da verificare).
- `config/` — configurazioni versionate (support).
- `data/` — dati ausiliari (support; da verificare).
- `docs/` — documentazione (support).
- `instructions/` — governance/Prompt Chain (support).
- `Lib/` — librerie locali (locale; da verificare).
- `logs/` — log locali (runtime; locale).
- `node_modules/` — dipendenze JS (locale; runtime).
- `observability/` — stack osservabilità (support).
- `output/` — output per‑cliente (runtime).
- `src/` — core del codice applicativo (core).
- `system/` — specifiche e policy di sistema (support).
- `tests/` — test (support).
- `tools/` — tool e script (support).
- `venv/` — virtualenv locale (locale; rigenerabile).

### File (depth 1)

- `.editorconfig` — regole di formattazione (support).
- `.env` — variabili locali (sensibile; locale).
- `.env.example` — esempio variabili (support).
- `.gitattributes` — policy Git (support).
- `.gitignore` — esclusioni Git (support).
- `.gitignore.bak` — backup gitignore (locale; da verificare).
- `.gitleaks.toml` — config Gitleaks (support).
- `.pre-commit-config.yaml` — hook pre-commit (support).
- `.secrets.baseline` — baseline scansione segreti (sensibile; support).
- `AGENTS.md` — entrypoint policy agent (support).
- `audit_repo.py` — script audit (da verificare).
- `bench.json` — dati benchmark (da verificare).
- `build_log.txt` — log build (locale; runtime).
- `CHANGELOG.md` — storico versioni (support).
- `CODE_OF_CONDUCT.md` — codice di condotta (support).
- `constraints.txt` — vincoli dipendenze (support).
- `CONTRIBUTING.md` — guida contribuzione (support).
- `cspell.json` — dizionario cSpell (support).
- `e2e.json` — config/risultati e2e (da verificare).
- `LICENSE.md` — licenza (support).
- `makefile` — comandi build/test (support).
- `MANIFEST.md` — manifesto/limiti (support).
- `mod_script.py` — script locale (da verificare).
- `mypy.ini` — config mypy (support).
- `package.json` — dipendenze JS (support).
- `package-lock.json` — lockfile npm (support).
- `patch_config_doc.py` — script doc/config (da verificare).
- `pyproject.toml` — config Python/tooling (support).
- `pyrightconfig.json` — config pyright (support).
- `pytest.ini` — config pytest (support).
- `pytest.log` — log pytest (locale; runtime).
- `pytest_again.log` — log pytest (locale; runtime).
- `pytest_full.log` — log pytest (locale; runtime).
- `qodana.json` — config Qodana (support).
- `qodana.licenses.yaml` — licenze Qodana (support).
- `qodana.sarif.json` — report Qodana (locale; runtime).
- `qodana.yaml` — config Qodana (support).
- `qodana-refresh.ps1` — script Qodana (support; da verificare).
- `README.md` — overview progetto (support).
- `remove_block.py` — script locale (da verificare).
- `requirements.in` — input dipendenze (support).
- `requirements.txt` — dipendenze (support).
- `requirements.txt.bak` — backup requirements (locale; da verificare).
- `requirements-dev.in` — input dev deps (support).
- `requirements-dev.txt` — dev deps (support).
- `requirements-optional.in` — input opzionali (support).
- `requirements-optional.txt` — deps opzionali (support).
- `SECURITY.md` — policy sicurezza (support).
- `service_account.json` — credenziali (sensibile; locale).
- `show_lines.py` — script locale (da verificare).
- `show_lines2.py` — script locale (da verificare).
- `show_lines3.py` — script locale (da verificare).
- `show_lines4.py` — script locale (da verificare).
- `SUMMARY.md` — indice/summary (support).
- `temp_gen_dummy_kb.txt` — output temporaneo (locale; da verificare).


## src/ — Core Architecture

La directory `src/` contiene il core applicativo. Qui risiedono pipeline, servizi semantici, UI, AI, storage e sicurezza; le altre aree del repo sono di supporto, runtime o locali.

Le responsabilità sono separate: `pipeline/` per l’orchestrazione I/O‑safe, `semantic/` per l’elaborazione contenuti, `ui/` per la UX Streamlit, `ai/` per risoluzione/configurazione modelli, `storage/` per persistenza, `security/` per controlli e protezione.

### Top‑level (depth 1)

- `__pycache__/` — bytecode (locale; cache).
- `adapters/` — adattatori per componenti esterni (support; da verificare).
- `ai/` — configurazione e runtime AI (core).
- `explainability/` — tracciabilità ed evidenze (core).
- `nlp/` — moduli NLP (core).
- `pipeline/` — orchestrazione core, path-safety, I/O, CLI e servizi di base (core).
- `security/` — controlli di sicurezza (core).
- `semantic/` — conversione, arricchimento, tagging e validazione (core).
- `storage/` — persistenza locale/SSoT (core).
- `timmy_kb/` — pacchetto principale (core).
- `timmy_kb.egg-info/` — metadata packaging (locale; runtime).
- `ui/` — interfaccia Streamlit, gating e componenti (core).
- `__init__.py` — entrypoint package (core).
- `kb_db.py` — DB/KB runtime (core; da verificare).
- `kg_models.py` — modelli KG (core; da verificare).

### Sotto‑aree (depth 2)

**adapters/**
`book_purity.py` (support; da verificare), `preview.py` (support).

**ai/**
`AGENTS.md` (support), `assistant_registry.py` (core), `check/` (support),
`client_factory.py` (core), `codex_runner.py` (core), `kgraph.py` (core),
`prototimmy.py` (core), `resolution.py` (core), `responses.py` (core),
`schemas/` (support), `types.py` (core), `vision_config.py` (core).

**explainability/**
`manifest.py` (core), `serialization.py` (core), `service.py` (core).

**nlp/**
`nlp_keywords.py` (core).

**pipeline/**
`AGENTS.md` (support), `capabilities/` (core), `cleanup_utils.py` (core),
`cli_runner.py` (core), `config_utils.py` (core), `constants.py` (core),
`content_utils.py` (core), `context.py` (core), `docker_utils.py` (core),
`drive/` (core), `drive_utils.py` (core), `embedding_utils.py` (core),
`env_utils.py` (core), `exceptions.py` (core), `file_utils.py` (core),
`frontmatter_utils.py` (core), `honkit_preview.py` (core), `import_utils.py` (core),
`ingest/` (core), `layout_summary.py` (core), `log_viewer.py` (support),
`logging_utils.py` (core), `metrics.py` (core), `observability_config.py` (support),
`oidc_utils.py` (core), `ontology.py` (core), `ownership.py` (core),
`path_utils.py` (core), `paths.py` (core), `proc_utils.py` (core),
`provision_from_yaml.py` (core), `qa_evidence.py` (core), `secret_checks.py` (core),
`settings.py` (core), `system_self_check.py` (core), `tracing.py` (core),
`types.py` (core), `vision_runner.py` (core), `vision_template.py` (core),
`workspace_bootstrap.py` (core), `workspace_layout.py` (core), `yaml_utils.py` (core).

**security/**
`authorization.py` (core), `masking.py` (core), `retention.py` (core), `throttle.py` (core).

**semantic/**
`AGENTS.md` (support), `api.py` (core), `auto_tagger.py` (core),
`book_readiness.py` (core), `config.py` (core), `context_paths.py` (core),
`contracts.py` (core), `convert_service.py` (core), `core.py` (core),
`document_ingest.py` (core), `embedding_service.py` (core),
`entities_extractor.py` (core), `entities_frontmatter.py` (core),
`entities_review.py` (core), `entities_runner.py` (core), `explain_pack.py` (core),
`exporters.py` (core), `frontmatter_service.py` (core), `layout_enricher.py` (core),
`lexicon.py` (core), `mapping_loader.py` (core), `nlp_runner.py` (core),
`normalizer.py` (core), `paths.py` (core), `pdf_utils.py` (core),
`redaction.py` (core), `review_writer.py` (core), `semantic_mapping.py` (core),
`spacy_extractor.py` (core), `tagging_service.py` (core), `tags_extractor.py` (core),
`tags_io.py` (core), `tags_validator.py` (core), `types.py` (core),
`validation.py` (core), `validators.py` (core), `vision_parser.py` (core),
`vision_provision.py` (core), `vision_utils.py` (core), `vocab_loader.py` (core).

**storage/**
`kb_store.py` (core), `tags_store.py` (core).

**timmy_kb/**
`cli/` (core), `logs/` (runtime; locale), `ui/` (core), `versioning.py` (core).

**ui/**
`AGENTS.md` (support), `app_core/` (core), `app_services/` (core), `chrome.py` (core),
`clients_store.py` (core), `components/` (core), `config_store.py` (core),
`const.py` (core), `constants.py` (core), `errors.py` (core),
`filters.py` (core), `fine_tuning/` (core), `gating.py` (core),
`imports.py` (core), `landing_slug.py` (core), `manage/` (core),
`navigation_spec.py` (core), `pages/` (core), `preflight.py` (core),
`semantic_progress.py` (core), `services/` (core), `theme/` (core),
`theme_enhancements.py` (core), `types.py` (core), `utils/` (core).
