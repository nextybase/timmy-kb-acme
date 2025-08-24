# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

> **Nota metodologica:** ogni nuova sezione deve descrivere chiaramente il contesto delle modifiche (Added, Changed, Fixed, Security, ecc.), specificando file e funzioni interessate. Gli aggiornamenti devono essere allineati con la documentazione (`docs/`) e riflessi in README/User Guide/Developer Guide quando impattano la UX o le API pubbliche. Le versioni MINOR/MAJOR vanno accompagnate da note di migrazione.

## [1.2.2] — 2025-08-24

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
