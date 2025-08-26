# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

> **Nota metodologica:** ogni nuova sezione deve descrivere chiaramente il contesto delle modifiche (Added, Changed, Fixed, Security, ecc.), specificando file e funzioni interessate. Gli aggiornamenti devono essere allineati con la documentazione (`docs/`) e riflessi in README/User Guide/Developer Guide quando impattano la UX o le API pubbliche. Le versioni MINOR/MAJOR vanno accompagnate da note di migrazione.

## [1.4.0] - 2025-08-26

### Added
- **Proc utils**: nuovo modulo `src/pipeline/proc_utils.py` con `run_cmd` (timeout/retry/backoff, logging strutturato), `wait_for_port`, helper Docker (`run_docker_preview`, `stop_docker_preview`).
- **Preview HonKit/GitBook**:
  - `src/pipeline/gitbook_preview.py`: build/serve in Docker, readiness check, stop best-effort.
  - `src/adapters/preview.py`: adapter semplice `start_preview/stop_preview`, default `gitbook-<slug>`, propagazione `redact_logs`.
- **Semantica**:
  - `src/semantic/tags_extractor.py`: copia PDF sicura + `emit_tags_csv` (schema esteso: `relative_path|suggested_tags|entities|keyphrases|score|sources`).
  - `src/semantic/tags_io.py`: `write_tagging_readme`, `write_tags_review_stub_from_csv` (dedup/normalize, path-safety, scrittura atomica).
  - `src/semantic/tags_review_validator.py`: validazione YAML + `write_validation_report`.
- **Documentazione interna**: sezione “SSoT scritture → `safe_write_text`” (I/O & Path-safety) con pattern minimi.
- **CI/QA**:
  - **Qodana**: configurazione consigliata (incluso controllo licenze/dependenze).
  - **GitHub Actions**: workflow CI con step separati **flake8**, **mypy**, **pytest**, cache pip e artifact dei log.

### Changed
- **SSoT scritture**: rimpiazzati `open(...).write(...)` con `safe_write_text` / `safe_write_bytes` e **guard-rail STRONG** `ensure_within` prima di ogni scrittura/eliminazione.
- **GitHub push** (`src/pipeline/github_utils.py`, refactor Patch 5):
  - Risoluzione branch via env (`GIT_DEFAULT_BRANCH`/`GITHUB_BRANCH`) con fallback `main`.
  - Creazione/ensure repo via PyGithub; clone in **working dir temporanea dentro la sandbox**; commit deterministico; push con retry.
  - **Force push governato**: `--force-with-lease` + allow-list branch e `force_ack` obbligatorio.
  - Autenticazione HTTP via `GIT_HTTP_EXTRAHEADER` (token non nei comandi); cleanup tmp idempotente; logging strutturato e redazione segreti.
- **Contenuti Markdown** (`src/pipeline/content_utils.py`):
  - Conversione annidata per categorie, fingerprint `.fp` per *skip if unchanged*, concorrenza per categoria.
  - `SUMMARY.md` e `README.md` generati in modo atomico e sicuro.
- **Orchestratore tagging** (`src/tag_onboarding.py`):
  - Download/copia PDF con path-safety; **CSV streaming atomico**; checkpoint HiTL; validazione YAML con report JSON.
- **Tool dummy** (`src/tools/gen_dummy_kb.py`): rimosso `print()`, logging strutturato, log sugli step PDF/CSV, scritture atomiche centralizzate.
- **Cleanup**:
  - `src/pipeline/cleanup_utils.py`: rimozione sicura di artefatti legacy (`book/.git`) con `ensure_within`.
  - `src/tools/cleanup_repo.py`: cancellazione repo remoto via **API (PyGithub)** con fallback automatico a **CLI `gh`**, owner auto-detected; messaggistica migliorata.
- **Consistenza YAML**: uniformato su estensione `.yaml` anche per configurazioni CI/Qodana.
- **Dipendenze**: versioni aggiornate/pinnate per ripetibilità build (PyGithub, google-api-python-client, PyYAML, docker, spaCy, ecc.).

### Fixed
- Eliminato rischio di **path traversal** su write/delete grazie a `ensure_within` su tutti i punti critici.
- Affidabilità preview HonKit: readiness check sulla porta e gestione container duplicati.
- Coerenza logging: rimosse stampe dirette; solo **logging strutturato**.

### Security
- Scritture **atomiche** ed **idempotenti**; backup `.bak` dove opportuno.
- Redazione automatica dei segreti nei log; autenticazione GitHub via header HTTP (niente token in argv).

### Known Issues
- La cancellazione del repo via API/CLI richiede permessi **admin** sul repository; in assenza di permessi si riceve 401/403 dalla API o errore dalla CLI. Lo strumento gestisce e logga il fallback, ma non può bypassare i permessi.

### Migration Notes
- Se presenti vecchi file `.yml`, rinominarli in `.yaml` per allineamento e per i riferimenti nei workflow/strumenti.

---

## 1.3.0 - 2025-08-26

### Changed
- Refactor orchestratori (`pre_onboarding.py`, `tag_onboarding.py`, `semantic_onboarding.py`) per rispettare le linee guida Codex:
  - Estrazione sottoprocedure in funzioni pure, unit-testabili (<80 righe).
  - Uniformata la gestione di fallback/adapters → ora tutte le funzioni usano `(context, logger, **opts)`.
- Migliorata la pipeline di tagging (`tag_onboarding.py`):
  - Passaggio a scrittura **CSV streaming riga-per-riga** con commit atomico.
  - Validazione YAML più robusta e reporting strutturato.
- Aggiornato `semantic_onboarding.py`:
  - Arricchimento frontmatter ottimizzato tramite dizionario inverso dei sinonimi (O(1) lookup).
  - Consolidato l’uso di `ensure_readme_summary` come fallback centralizzato per README/SUMMARY.

### Documentation
- Aggiornati **Architecture.md**, **Developer Guide** e **Coding Rules** (v1.3.0):
  - Documentati i nuovi invarianti (funzioni pure negli orchestratori, streaming CSV, enrichment indicizzato).
  - Allineati esempi di logging ed error handling.
  - Esplicitato l’uso centralizzato degli adapter e delle firme coerenti.


## [1.2.2] fix generici e armonizzazione funzioni - 2025-08-26

### Added
- **Test suite di configurazione (pytest + Pydantic)**
  - `tests/test_config_utils.py`: copertura completa dei moduli `pipeline.config_utils` (Settings, client config, pre-onboarding, scritture atomiche, aggiornamento Drive IDs).
  - Fixture `conftest.py` consolidata: genera sempre una sandbox dummy pulita (`--overwrite`), forza ambiente UTF-8 e gestisce teardown automatico salvo `KEEP_DUMMY_KB=1`.
- **Refactor tool interattivo**
  - `src/tools/refactor_tool.py`: menu interattivo grafico (box ASCII) con 3 voci:
    1. 🔎 Trova (solo ricerca)  
    2. ✏️ Trova & Sostituisci  
    3. 📌 Cerca TODO/FIXME  
  - Logging strutturato, dry-run con diff unificato leggibile, estendibile per futuri strumenti di refactor.

### Changed
- **`src/semantic/normalizer.py`**
  - Bug fix: `normalize_tags` ora ritorna correttamente `normed` (prima restituiva `""`).
  - Robustezza mapping: canonical/merge normalizzati a lowercase; coercizione prudente delle liste `synonyms`.
- **`src/tools/cleanup_repo.py`**
  - Flusso interattivo semplificato:
    - Conferma obbligatoria per la cancellazione locale di `output/timmy-kb-<slug>`, evidenziando che è irreversibile.
    - Solo se confermata, viene chiesto se eliminare anche il repo GitHub remoto (`gh repo delete`).
  - Uso coerente di `pipeline.logging_utils.redact_secrets` al posto di `env_utils`.

### Fixed
- Import path per `pipeline.*` nei tool (`gen_dummy_kb.py`, `cleanup_repo.py`, `refactor_tool.py`) resi consistenti con il bootstrap della cartella `src/`.
- Errori di compatibilità Windows (`ModuleNotFoundError: pipeline`) gestiti allineando sys.path a livello di progetto.

### Migration notes
- Per avviare i test singoli:
  ```bash
  pytest tests/test_config_utils.py -v
  pytest tests/test_dummy_pipeline.py -v


## [1.2.2] - 2025-08-25

### Added
- **Test suite dummy (pytest + Pydantic)**:
  - `tests/conftest.py`: fixture `dummy_kb` che rigenera la sandbox con `--overwrite` e valida i file chiave.
  - `tests/test_dummy_pipeline.py`: 4 test (struttura, coerenza CSV↔PDF, idempotenza semantic, assenza `contrattualistica/`).
- **Robustezza Windows nei test**: forzato `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` al lancio di `gen_dummy_kb.py`.

### Changed
- **`src/tools/gen_dummy_kb.py`** riscritto:
  - Genera la sandbox dummy completa da `config/*.yaml`.
  - Produce PDF dummy coerenti con `pdf_dummy.yaml`.
  - Copia `cartelle_raw.yaml` in `semantic/` e crea `semantic_mapping.yaml` con blocco `semantic_tagger` default.
  - Genera `tags_raw.csv` tramite i moduli semantic (`extract_semantic_candidates → normalize_tags → render_tags_csv`).
- **`src/tag_onboarding.py`**:
  - `_emit_tags_csv` ora produce path base-relative (`raw/...`) e colonne extra (`entities`, `keyphrases`, `score`, `sources`) per compatibilità futura.

### Fixed
- Crash su Windows (`UnicodeEncodeError` da emoji ✅, `NameError: json`).
- Path incoerenti tra CSV generati da strumenti diversi (ora formato unificato).
- Errore `relative_to` su `contrattualistica/` (cartella rimossa per design).

### Removed
- Generazione locale della cartella `contrattualistica/` nel dummy.

### Migration notes
- Rigenera la sandbox dummy:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy --name "Cliente Dummy" --overwrite

## [1.2.1] Intermedio — 2025-08-25

> Release intermedia di consolidamento, applicata dopo le indicazioni di Codex e completata con refactor/test end-to-end sugli orchestratori. Focus su **pipeline core**; l’area semantica resta placeholder per la fase successiva.

### Changed
- **github_utils**
  - Estratto `_collect_md_files`, `_ensure_or_create_repo`, `_push_with_retry` e helper correlati per ridurre complessità di `push_output_to_github` (~400→ <150 righe).
  - Migliorata leggibilità e testabilità mantenendo lo stesso comportamento.
- **onboarding_full.py**
  - Orchestratore snellito: usa `_git_push` dedicato con error handling coerente.
  - Conferme interattive più chiare, non-interactive totalmente silente.
- **logging_utils**
  - Refactor completo: `get_structured_logger` ora unica entrypoint.
  - Filtri di contesto e redazione applicati a tutti i call-sites.
  - Formatter coerente console/file con extra (`slug`, `run_id`, `branch`, `repo`).
- **Orchestratori (pre_onboarding, tag_onboarding, semantic_onboarding)**
  - Allineati a nuovo logging strutturato.
  - Path-safety rafforzata su tutti i call-site I/O di pipeline core.

### Fixed
- Nessun uso residuo di `FileNotFoundError`/`NotADirectoryError` in pipeline core (`src/pipeline`, `src/adapters`).
- Eliminati logger fallback o duplicati: tutti i moduli passano da `logging_utils`.

### Migration notes
- Usare sempre `get_structured_logger(...)` per creare logger.
- Gestire la redazione solo via `context.redact_logs` (inizializzato da `compute_redact_flag`).
- L’area semantica (`semantic_extractor`, ecc.) resta ancora con built-in exceptions: da aggiornare in release successiva.


## [1.2.1] — 2025-08-24

> Hardening trasversale: SSoT per path-safety, redazione log centralizzata e orchestratori resi più coesi.

### Added
- **logging_utils**
  - Filtro di redazione centralizzato (mascheratura su `msg/args/extra`).
  - Helper riusabili: `mask_partial`, `tail_path`, `mask_id_map`, `mask_updates`.
  - Metriche leggere: `metrics_scope`, `log_with_metrics`.

### Changed
- **env_utils**
  - Reso *puro*: nessuna mascheratura; introdotta `compute_redact_flag(env, log_level)` come fonte unica del flag.
  - Utilities per governance del force-push: `get_force_allowed_branches`, `is_branch_allowed_for_force`.
- **path_utils**
  - `ensure_within(base, target)` promosso a **Single Source of Truth** per path-safety; `is_safe_subpath` resta SOFT.
  - Aggiunti `ensure_valid_slug`, `sanitize_filename`, `sorted_paths`; cache regex slug + fallback robusto.
- **cleanup_utils**
  - Rimozioni protette: uso di `ensure_within` prima di delete; log strutturati coerenti.
- **github_utils**
  - Hardening push: selezione deterministica file, working dir temporanea sotto base cliente, retry con `pull --rebase`, lease per force-push e allow-list branch.
  - Env sanificato per subprocess; redazione opzionale lato logger.
- **gitbook_preview**
  - Build/serve via `proc_utils.run_cmd`; scritture atomiche (`safe_write_file`); `ensure_within` sulle destinazioni; `wait_until_ready` e stop best-effort.
- **content_utils**
  - Conversione RAW→BOOK con gerarchie annidate; fingerprint per skip idempotente; nomi file sanificati; scritture atomiche e path-safety; generatori `SUMMARY.md`/`README.md`.
- **drive/download**
  - Scansione BFS, idempotenza (MD5/size), verifica integrità post-download, path-safety forte e log redatti.
- **Orchestratori**
  - `pre_onboarding.py`: estratto `_sync_env()`, validazione slug centralizzata, redazione propagata.
  - `tag_onboarding.py`: CSV + stub semantico con scritture atomiche e guardie `ensure_within`.
  - `semantic_onboarding.py`: conversione/enrichment/README+SUMMARY/preview (nessun push).
  - `onboarding_full.py`: solo **push GitHub** (con conferma solo in interattivo).

### Fixed
- Import uniformati: **spostata la mascheratura** da `env_utils` a `logging_utils` (aggiornati i call-sites).
- Robustezza frontmatter/preview: gestione assenza PyYAML e correzioni su path relativi/assoluti.

### Security / Hardening
- **Path-safety** consolidata con `ensure_within` su tutte le scritture/copie/rimozioni sensibili.
- **Scritture atomiche** come default per file generati dalla pipeline.

### Migration notes
- Importare ora `redact_secrets` da `pipeline.logging_utils`.
- Inizializzare il flag di redazione negli orchestratori appena caricato il contesto:
  ```python
  from pipeline.env_utils import compute_redact_flag
  if not hasattr(context, "redact_logs"):
      context.redact_logs = compute_redact_flag(context.env, getattr(context, "log_level", "INFO"))

---

## [1.2.1] — 2025-08-24

> Release focalizzata su refactor, documentazione e split chiaro degli orchestratori.  
> PR correlate: **PR-5** (Semantic Onboarding), **PR-6** (Docs v1.2.1).

### Added
- **Nuovo orchestratore**
  - `src/semantic_onboarding.py`: gestisce conversione RAW→BOOK, arricchimento frontmatter e preview Docker; nessun push GitHub.
- **Docs**
  - Aggiunta guida aggiornata per `semantic_onboarding` nei manuali (User/Developer/Architecture).

### Changed
- **Orchestratori**
  - `onboarding_full.py`: ridotto a gestire solo il **push GitHub** (in futuro anche GitBook).
  - Precedente logica di conversione/enrichment/preview spostata in `semantic_onboarding.py`.
- **Adapter**
  - Uso uniforme di `ensure_within` da `pipeline.path_utils` come SSoT per path-safety.
- **Tool**
  - `gen_dummy_kb.py`: refactor secondo le nuove regole di atomicità e path-safety.

### Fixed
- Spostato l’import `from __future__ import annotations` all’inizio dei file per evitare `SyntaxError`.
- Allineamento docstring e logica di gestione dei file tra moduli e orchestratori.

### Documentation
- Aggiornati a v1.2.1:
  - `docs/architecture.md`: riflesso lo split orchestratori (`semantic_onboarding` vs `onboarding_full`).
  - `docs/developer_guide.md`: bootstrap `ClientContext`, policy redazione, responsabilità orchestratori.
  - `docs/user_guide.md`: nuovo flusso operativo con `semantic_onboarding`.
  - `docs/coding_rules.md`: chiariti punti su atomicità e adapter.
  - `docs/policy_push.md`: rivista policy di pubblicazione.
  - `README.md` e `docs/index.md`: aggiornati esempi CLI e versioni.

### Migration notes
- Usare ora `semantic_onboarding.py` per conversione/enrichment/preview.
- `onboarding_full.py` va utilizzato solo per il push.
- Nei moduli, sostituire eventuali riferimenti a `file_utils.ensure_within` con `path_utils.ensure_within`.

---

## [1.2.0] — 2025-08-24

> Release di stabilizzazione e hardening della pipeline. Introduce fallback uniformi, preview adapter, scritture atomiche e aggiornamento completo della documentazione.
> PR correlate: **PR-1** (Redaction SSoT), **PR-2** (Fallback & Preview adapter), **PR-3** (Atomic FS & Path-safety), **PR-4** (API cleanup & Docs).

### Added
- **Adapters**
  - `src/adapters/content_fallbacks.py`: `ensure_readme_summary(context, logger)` con fallback standard e idempotenti per `README.md` e `SUMMARY.md`.
  - `src/adapters/preview.py`: `start_preview(context, logger, *, port=4000, container_name=None)` e `stop_preview(logger, *, container_name=None)`; propagazione automatica `context.redact_logs`.
- **File utilities**
  - `pipeline/file_utils.py`: `safe_write_text`, `safe_write_bytes` (temp + `os.replace` atomico + fsync best-effort) e `ensure_within` (guardia anti path traversal).
- **Docs**
  - Nuovo `docs/SUMMARY.md` (indice top-level per GitHub/HonKit).

### Changed
- **Orchestratori**
  - `src/onboarding_full.py`:
    - Usa `adapters.content_fallbacks.ensure_readme_summary` per i fallback; rimosse logiche inline.
    - Preview unificata via `adapters.preview.start_preview/stop_preview`.
    - Scritture frontmatter con `safe_write_text` + `ensure_within`.
    - Firma helpers interna allineata a stile `(context, logger, **opts)`.
  - `src/tag_onboarding.py`:
    - Emissione `tags_raw.csv`, `README_TAGGING.md`, `tags_reviewed.yaml`, `tags_review_validation.json` con `safe_write_text`; guardie `ensure_within`/`is_safe_subpath`.
    - Fallback `context.redact_logs` se mancante → `compute_redact_flag()`.
  - `src/pre_onboarding.py`:
    - Risoluzione robusta `YAML_STRUCTURE_FILE`; messaggistica più chiara; uso coerente di `repo_root_dir` ed env helpers (no cambi funzionali in assenza di Drive).
- **ENV/Redaction**
  - `pipeline/env_utils.py`: `compute_redact_flag(env, log_level)` come single source of truth; orchestratori inizializzano `context.redact_logs` se non presente.
- **Demo tool**
  - `src/tools/gen_dummy_kb.py`: migrazione delle scritture a `safe_write_text` e verifiche path (dove applicabile).

### Fixed
- Allineata firma `ensure_readme_summary(...)` negli orchestratori (rimosso argomento non supportato `book_dir`).
- Log più robusti e non verbosi su assenza opzionale di PyYAML; migliorata resilienza del parsing frontmatter.

### Security / Hardening
- **Scritture atomiche di default** per file generati dalla pipeline → evita file troncati su interruzioni.
- **Path-safety**: `ensure_within`/`is_safe_subpath` applicati alle destinazioni sensibili.
- **Redazione log uniforme**: `compute_redact_flag` applicato/propagato agli adapter (preview) e agli orchestratori.

### Deprecated
- `is_log_redaction_enabled(context)` rimane per retro-compat ma **deprecato** in favore di `compute_redact_flag`.
- Uso diretto e sporadico di `os.environ` negli orchestratori → **usare** `env_utils.get_env_var/get_bool/get_int`.

### Documentation
- Aggiornati e riallineati:
  - `docs/architecture.md` (SSoT `repo_root_dir`, fallback uniformi, scritture atomiche).
  - `docs/developer_guide.md` (bootstrap `ClientContext`, policy redazione, responsabilità orchestratori vs moduli).
  - `docs/user_guide.md` (flussi interattivo/CLI, opzioni preview/push, troubleshooting).
  - `docs/coding_rule.md` (regole I/O sicure, atomicità, logging).
  - `docs/policy_push.md` (uso `--no-push`, `--force-push` + `--force-ack`, `GIT_DEFAULT_BRANCH`).
  - `docs/versioning_policy.md` (SemVer leggero, requisiti di release).
  - `docs/index.md` e **README** (sezioni riviste, esempi CLI aggiornati).

### Migration notes
- Rimpiazzare nei flussi:
  - Fallback inline → `adapters.content_fallbacks.ensure_readme_summary(context, logger)`.
  - Chiamate dirette a `pipeline.gitbook_preview.*` → `adapters.preview.start_preview/stop_preview`.
  - `Path.write_text(...)` → `safe_write_text(...)` (+ `ensure_within` o `is_safe_subpath`).
- Inizializzare `context.redact_logs` **subito dopo** `ClientContext.load(...)` se non presente:
  ```python
  from pipeline.env_utils import compute_redact_flag
  if not hasattr(context, "redact_logs"):
      context.redact_logs = compute_redact_flag(context.env, log_level="INFO")

## [1.1.0] — 2025-08-23 · Lancio baseline stabile

### Added
- Prima versione stabile della pipeline con orchestratori separati (`pre_onboarding`, `tag_onboarding`, `onboarding_full`).
- Struttura modulare in `src/pipeline/` con gestione centralizzata di:
  - logging (`logging_utils`),  
  - eccezioni tipizzate (`exceptions`),  
  - variabili di ambiente e redazione (`env_utils`),  
  - configurazioni e path safety (`config_utils`, `path_utils`).
- Documentazione completa in `docs/` (User Guide, Developer Guide, Architecture, Coding Rules, Policy Push, Versioning).

### Changed
- Allineamento di orchestratori e moduli al principio **UX vs logica tecnica**: prompt e `sys.exit()` confinati agli orchestratori; moduli puri e testabili.
- Output standardizzato in `output/timmy-kb-<slug>/` con sottocartelle (`raw`, `book`, `semantic`, `config`, `logs`).

### Notes
- Questa versione rappresenta la **base di partenza ufficiale**: da qui in poi ogni refactor, fix o nuova feature dovrà essere registrata come incremento SemVer e mantenere la compatibilità documentale.
