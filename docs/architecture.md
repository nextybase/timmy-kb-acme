# Architettura — Timmy-KB (v1.2.0)

Questa pagina descrive l’architettura **aggiornata** del sistema: componenti, flussi end‑to‑end, struttura del repository e le API interne su cui si fonda la pipeline. Gli sviluppatori devono sempre riferirsi anche a [Developer Guide](developer_guide.md) e alle regole di codifica per estendere o modificare il codice, privilegiando il riuso di funzioni esistenti e proponendo aggiornamenti se necessario.

---

## Panorama generale

- **Obiettivo**: trasformare PDF locali in una **KB Markdown AI‑ready**, arricchita semanticamente e pronta per anteprima (HonKit/Docker) e push Git.
- **Scope**: RAW è **solo locale** (`output/timmy-kb-<slug>/raw`). Google Drive è usato **solo** nel pre‑onboarding per creare la struttura remota e caricare `config.yaml`.
- **Separazione ruoli**: orchestratori (UX/CLI, exit codes) vs moduli tecnici (logica pura, nessun prompt/exit).
- **PR1‑PR4**: introduzione di path‑safety, scritture atomiche, adapter uniformi per contenuti e preview, allineamento firme API.

---

## Flusso end‑to‑end (pipeline)

**1) pre\_onboarding → setup locale + (opz.) struttura Drive**

- Input: `slug` (e nome cliente, se interattivo); opz.: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `YAML_STRUCTURE_FILE`.
- Azioni: crea struttura locale; risolve YAML struttura; (se configurato) crea struttura su Drive; carica `config.yaml` nella root cliente su Drive; aggiorna `config.yaml` locale con gli ID remoti.
- Output: `output/timmy-kb-<slug>/{raw,book,semantic,config,logs}` + `config.yaml` aggiornato; opz.: mappa cartelle Drive.

**2) tag\_onboarding → scoperta tag e vocabolario**

- Input: PDF in `raw/`.
- Azioni: analisi nominale/euristica; produce/aggiorna `semantic/tags.yaml`.
- Output: `semantic/tags.yaml` (tag canonicali, sinonimi, aree).

**3) onboarding\_full → conversione + enrichment + preview + push**

- Input: `raw/` + `semantic/tags.yaml`.
- Azioni: PDF→MD in `book/`; arricchimento frontmatter (tags/areas); generazione `README.md` e `SUMMARY.md` (repo util → adapter fallback atomico); preview HonKit (Docker, opz.); push Git (opz.).
- Output: Markdown pronti in `book/`; anteprima su `localhost:<port>` (se attiva); commit/push (se abilitato).

---

## Struttura del repository

```
repo/
├─ config/
│  └─ cartelle_raw.yaml                  # YAML struttura cartelle (pre-onboarding)
├─ docs/
│  ├─ README.md                          # guida utente rapida (pubblico)
│  ├─ user_guide.md                      # guida utente estesa
│  ├─ developer_guide.md                 # guida per sviluppatori
│  ├─ architecture.md                    # questa pagina
│  ├─ policy_push.md                     # policy di pubblicazione
│  └─ versioning_policy.md               # regole di versioning
├─ src/
│  ├─ pre_onboarding.py                  # orchestratore setup + (opz.) Drive
│  ├─ tag_onboarding.py                  # orchestratore tagging semantico
│  ├─ onboarding_full.py                 # orchestratore conversione/enrichment/preview/push
│  ├─ config/                            # fallback config YAML
│  │  └─ cartelle_raw.yaml               # fallback se manca in /config
│  ├─ adapters/                          # adapter centralizzati (PR-2+)
│  │  ├─ content_fallbacks.py            # README/SUMMARY fallback atomici
│  │  └─ preview.py                      # gestione preview Docker/HonKit
│  └─ pipeline/
│     ├─ __init__.py
│     ├─ constants.py                    # OUTPUT_DIR_NAME, LOGS_DIR_NAME, ...
│     ├─ context.py                      # ClientContext (+ load helpers)
│     ├─ exceptions.py                   # PipelineError, ConfigError, EXIT_CODES, ...
│     ├─ env_utils.py                    # get_env_var, compute_redact_flag
│     ├─ logging_utils.py                # get_structured_logger
│     ├─ path_utils.py                   # validate_slug, sorted_paths, sanitize_filename, is_safe_subpath
│     ├─ file_utils.py                   # scritture atomiche + path safety (PR-3)
│     ├─ config_utils.py                 # get/write/update client config
│     ├─ content_utils.py                # convert & generate markdown utilities
│     ├─ gitbook_preview.py              # run_gitbook_docker_preview, stop_container_safely
│     ├─ github_utils.py                 # push_output_to_github
│     ├─ drive_utils.py                  # API di alto livello per Drive
│     └─ drive/
│        ├─ __init__.py
│        ├─ upload.py                    # helper di caricamento/config su Drive
│        ├─ client.py                    # gestione autenticazione e API Google Drive
│        ├─ download.py                  # download ricorsivo e sicuro da Google Drive
└─ output/                               # (GENERATO) per‑cliente: timmy-kb-<slug>/{raw,book,semantic,config,logs}
```

> Nota: la cartella `output/` è generata a runtime e non va versionata.

---

## Funzioni principali (API interne)

### pipeline.logging\_utils

- `get_structured_logger(name, log_file=None, context=None, run_id=None)` → logger strutturato (console/file), safe per segreti.

### pipeline.exceptions

- `PipelineError`, `ConfigError`, `InvalidSlug` — eccezioni principali.
- `EXIT_CODES` — mappa eccezioni→exit code.

### pipeline.context

- `ClientContext.load(slug, *, interactive, require_env, run_id)` → inizializza contesto cliente.
  - Campi: `slug`, `base_dir`, `raw_dir`, `book_dir`, `semantic_dir`, `config_dir`, `logs_dir`, `config_path`, `env`, `settings`, `redact_logs`, `repo_root_dir`.

### pipeline.config\_utils

- `get_client_config`, `write_client_config_file`, `update_config_with_drive_ids`

### pipeline.env\_utils

- `get_env_var`, `compute_redact_flag`

### pipeline.path\_utils

- `validate_slug`, `sorted_paths`, `sanitize_filename`, `is_safe_subpath`

### pipeline.file\_utils (PR‑3)

- `ensure_within`, `safe_write_text`, `safe_write_bytes`

### pipeline.drive\_utils (solo pre‑onboarding)

- `get_drive_service`, `create_drive_folder`, `create_drive_structure_from_yaml`, `upload_config_to_drive_folder`, `create_local_base_structure`

### pipeline.content\_utils (onboarding\_full)

- `convert_files_to_structured_markdown`, `generate_summary_markdown`, `generate_readme_markdown`, `validate_markdown_dir`

### adapters.content\_fallbacks (PR‑2/PR‑3)

- `ensure_readme_summary(context, logger, *, force=False)`

### adapters.preview (PR‑2/PR‑4)

- `start_preview(context, logger, *, port=4000, container_name=None, wait_on_exit=False)`
- `stop_preview(logger, *, container_name)`

### pipeline.gitbook\_preview (low‑level)

- `run_gitbook_docker_preview`, `stop_container_safely`

### pipeline.github\_utils (opz.)

- `push_output_to_github`

---

## Costanti principali

Da `pipeline.constants`:

- `OUTPUT_DIR_NAME`, `LOGS_DIR_NAME`, `LOG_FILE_NAME`, `REPO_NAME_PREFIX`

---

## Variabili d’ambiente

- `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `YAML_STRUCTURE_FILE`
- `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH`
- `LOG_REDACTION`, `ENV`, `CI`

---

## Risoluzione del file YAML di struttura

Ordine di ricerca (pre‑onboarding):

1. `YAML_STRUCTURE_FILE` (se impostata)
2. `config/cartelle_raw.yaml` (root repo)
3. `src/config/cartelle_raw.yaml` (fallback)

Errore esplicito se nessun candidato esiste.

---

## Gestione errori e exit codes

- Eccezioni tipiche: `ConfigError`, `PipelineError`, `InvalidSlug`.
- Codici: `0` OK, `2` ConfigError, `30` PreviewError, `40` PushError.

---

## Invarianti architetturali

- **RAW locale**: conversione/enrichment indipendenti da Drive.
- **Idempotenza**: operazioni ripetibili senza duplicati.
- **Sicurezza**: redazione log uniforme; path‑safety; scritture atomiche.
- **Trasparenza**: log strutturati con `run_id` per correlazione.
- **API coerenti**: tutte le funzioni esposte hanno firma `(context, logger, **opts)` o variante coerente (PR‑4).

---

