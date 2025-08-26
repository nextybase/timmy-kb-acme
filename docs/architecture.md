# Architettura — Timmy-KB (v1.2.2)

Questa pagina descrive l’architettura **aggiornata** del sistema: componenti, flussi end‑to‑end, struttura del repository e le API interne su cui si fonda la pipeline. Gli sviluppatori devono sempre riferirsi anche a [Developer Guide](developer_guide.md) e alle regole di codifica per estendere o modificare il codice, privilegiando il riuso di funzioni esistenti e proponendo aggiornamenti se necessario.

---

## Panorama generale

- **Obiettivo**: trasformare PDF locali in una **KB Markdown AI‑ready**, arricchita semanticamente e pronta per anteprima (HonKit/Docker) e push Git.
- **Scope**: RAW è **solo locale** (`output/timmy-kb-<slug>/raw`). Google Drive è usato **solo** nel pre‑onboarding per creare la struttura remota e caricare `config.yaml`.
- **Separazione ruoli**: orchestratori (UX/CLI, exit codes) vs moduli tecnici (logica pura, nessun prompt/exit).
- **Struttura e Security**: path‑safety, scritture atomiche, adapter uniformi per contenuti/preview, allineamento firme API.
- **SSoT path‑safety**: `ensure_within` è **single source of truth** in `pipeline.path_utils`.
- **Split orchestratori**: conversione/enrichment/preview in `semantic_onboarding.py`; push in `onboarding_full.py`.
- **Testing**: la KB dummy viene generata da `tools/gen_dummy_kb.py` ed è validata tramite i test in `tests/`, che verificano coerenza PDF↔CSV ed enrichment semantico.

---

## Flusso end‑to‑end (pipeline)

**1) pre_onboarding → setup locale + (opz.) struttura Drive**

- Input: `slug` (e nome cliente, se interattivo); opz.: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `YAML_STRUCTURE_FILE`.
- Azioni: crea struttura locale; risolve YAML struttura; (se configurato) crea struttura su Drive; carica `config.yaml` nella root cliente su Drive; aggiorna `config.yaml` locale con gli ID remoti.
- Output: `output/timmy-kb-<slug>/{raw,book,semantic,config,logs}` + `config.yaml` aggiornato; opz.: mappa cartelle Drive.

**2) tag_onboarding → tagging semantico (HiTL)**

- Input: PDF in `raw/`.
- Azioni: genera `semantic/tags_raw.csv` (euristiche su path/filename), checkpoint HiTL con stub `tags_reviewed.yaml` e `README_TAGGING.md`.
- Output: `semantic/tags_raw.csv` + stub revisione.

**3) semantic_onboarding → conversione + enrichment + preview**

- Input: `raw/` + (opz.) `semantic/tags_reviewed.yaml`.
- Azioni: PDF→MD in `book/`; arricchimento frontmatter (tags/areas); generazione `README.md` e `SUMMARY.md` (repo util → adapter fallback atomico); avvio preview HonKit in Docker con chiusura esplicita.
- Output: Markdown pronti in `book/`; anteprima su `localhost:<port>`.

**4) onboarding_full → push (e integrazioni)**

- Input: `book/` pronto.
- Azioni: push GitHub via `github_utils`. In roadmap: collegamento GitBook.
- Output: commit/push su repo remoto.

---

## Struttura del repository

```
repo/
├─ README.md                  # documentazione principale
├─ config/
│  ├─ config.yaml                      # bootstrap globale (defaults iniziali)
│  ├─ .env.example                     # template variabili d'ambiente
│  ├─ cartelle_raw.yaml                # struttura cartelle RAW (pre_onboarding)
│  ├─ pdf_dummy.yaml                   # fixture per tools/gen_dummy_kb.py
│  └─ tags_template.yaml               # template vocabolario tag (facoltativo)
├─ docs/
│  ├─ index.md                         # indice generale della documentazione
│  ├─ user_guide.md
│  ├─ developer_guide.md
│  ├─ architecture.md                  # questa pagina
│  ├─ coding_rules.md
│  ├─ policy_push.md
│  └─ versioning_policy.md
├─ src/
│  ├─ pre_onboarding.py                # setup locale + (opz.) Drive
│  ├─ tag_onboarding.py                # tagging semantico (CSV/review/validator)
│  ├─ semantic_onboarding.py           # conversione/enrichment/preview (NO push)
│  ├─ onboarding_full.py               # solo push GitHub (e futuri collegamenti)
│  ├─ tools/
│  │  └─ gen_dummy_kb.py               # generatore KB di test (RAW+BOOK+semantic)
│  ├─ adapters/
│  │  ├─ content_fallbacks.py          # README/SUMMARY fallback atomici
│  │  └─ preview.py                    # gestione preview Docker/HonKit
│  ├─ semantic/                        # moduli di tagging e enrichment semantico
│  │  ├─ auto_tagger.py
│  │  ├─ config.py
│  │  ├─ normalizer.py
│  │  ├─ review_writer.py
│  │  ├─ semantic_extractor.py
│  │  ├─ semantic_mapping.py
│  │  ├─ tags_extractor.py
│  │  ├─ tags_io.py
│  │  └─ tags_validator.py
│  └─ pipeline/
│     ├─ constants.py                  # OUTPUT_DIR_NAME, LOGS_DIR_NAME, ...
│     ├─ context.py                    # ClientContext (+ load helpers)
│     ├─ exceptions.py                 # PipelineError, ConfigError, EXIT_CODES, ...
│     ├─ env_utils.py                  # get_env_var, compute_redact_flag
│     ├─ logging_utils.py              # get_structured_logger
│     ├─ path_utils.py                 # validate_slug, sorted_paths, sanitize_filename,
│     │                                 # is_safe_subpath, ensure_within (SSoT)
│     ├─ file_utils.py                 # safe_write_text/bytes (scritture atomiche)
│     ├─ config_utils.py               # get/write/update client config
│     ├─ content_utils.py              # convert & generate markdown utilities
│     ├─ github_utils.py               # push_output_to_github
│     └─ drive_utils.py                # API di alto livello per Drive
└─ output/                       # (GENERATO) per‑cliente: timmy-kb-<slug>/{raw,book,semantic,config,logs}
```

---

## Funzioni principali (API interne)

### pipeline.logging_utils

- `get_structured_logger(name, log_file=None, context=None, run_id=None)` → logger strutturato (console/file), safe per segreti.

### pipeline.exceptions

- `PipelineError`, `ConfigError`, `InvalidSlug` — eccezioni principali.
- `EXIT_CODES` — mappa eccezioni→exit code.

### pipeline.context

- `ClientContext.load(slug, *, interactive, require_env, run_id)` → inizializza contesto cliente.
  - Campi: `slug`, `base_dir`, `raw_dir`, `book_dir`, `semantic_dir`, `config_dir`, `logs_dir`, `config_path`, `env`, `settings`, `redact_logs`, `repo_root_dir`.

### pipeline.config_utils

- `get_client_config`, `write_client_config_file`, `update_config_with_drive_ids`

### pipeline.env_utils

- `get_env_var`, `compute_redact_flag`

### pipeline.path_utils

- `validate_slug`, `sorted_paths`, `sanitize_filename`, `is_safe_subpath`, `ensure_within` *(SSoT: guardia STRONG basata su **`Path.resolve()`** + **`relative_to()`**)*.

### pipeline.file_utils

- `safe_write_text`, `safe_write_bytes`
  - Scritture atomiche con temp file + `os.replace`, fsync best‑effort.

### pipeline.drive_utils (solo pre‑onboarding)

- `get_drive_service`, `create_drive_folder`, `create_drive_structure_from_yaml`, `upload_config_to_drive_folder`, `create_local_base_structure`

### pipeline.content_utils (conversione)

- `convert_files_to_structured_markdown`, `generate_summary_markdown`, `generate_readme_markdown`, `validate_markdown_dir`

### adapters.content_fallbacks

- `ensure_readme_summary(context, logger, *, force=False)`

### adapters.preview

- `start_preview(context, logger, *, port=4000, container_name=None, wait_on_exit=False)`
- `stop_preview(logger, *, container_name)`

### semantic (moduli)

- `auto_tagger.py` → tagging automatico dei PDF.
- `config.py` → configurazioni e costanti per l’arricchimento.
- `normalizer.py` → normalizzazione dei tag.
- `review_writer.py` → generazione file di revisione.
- `semantic_extractor.py` → estrazione concetti dai Markdown【577†source】.
- `semantic_mapping.py` → gestione e normalizzazione mapping semantico【578†source】.
- `tags_extractor.py` → estrazione dei tag dai PDF.
- `tags_io.py` → I/O su CSV, YAML e README tagging.
- `tags_validator.py` → validazione dei file di tagging.

### semantic_onboarding

- Converte RAW→BOOK, arricchisce frontmatter, genera README/SUMMARY, avvia preview Docker e chiede se fermarla prima di uscire. **Nessun push.**

### pipeline.github_utils

- `push_output_to_github`

### onboarding_full

- Esegue esclusivamente il **push GitHub** (e in futuro l'integrazione GitBook). Accetta un `book/` già pronto da `semantic_onboarding`.

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
- **API coerenti**: tutte le funzioni esposte hanno firma `(context, logger, **opts)` o variante coerente.
- **Compatibilità**: tool e orchestratori devono funzionare anche su Windows (gestione encoding/log emoji).

