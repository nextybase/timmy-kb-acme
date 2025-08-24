# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

> **Nota metodologica:** ogni nuova sezione deve descrivere chiaramente il contesto delle modifiche (Added, Changed, Fixed, Security, ecc.), specificando file e funzioni interessate. Gli aggiornamenti devono essere allineati con la documentazione (`docs/`) e riflessi in README/User Guide/Developer Guide quando impattano la UX o le API pubbliche. Le versioni MINOR/MAJOR vanno accompagnate da note di migrazione.

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
