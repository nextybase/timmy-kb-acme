# Architettura Tecnica – Timmy-KB

Questo documento descrive in dettaglio l’architettura di **Timmy-KB**, con un focus particolare sul flusso degli orchestratori, le funzioni importate, le variabili passate, le fonti dati utilizzate e il ruolo dei file chiave, basandosi sul codice effettivo presente in `src/onboarding_full.py`.

---

## 📂 Struttura del repository
```
root/
 ├── src/
 │    ├── pre_onboarding.py      # orchestratore fase 0 (crea struttura/config)
 │    ├── onboarding_full.py     # orchestratore end-to-end (download → md → preview → push)
 │    ├── pipeline/              # moduli core della pipeline (drive/github/utils/logging/…)
 │    ├── semantic/              # parsing, tagging, mapping e arricchimento semantico
 │    └── tools/                 # utility CLI, validatori, refactoring
 ├── config/                     # YAML (cartelle_raw.yaml, mapping, template)
 ├── output/                     # output Markdown/YAML generati per cliente
 ├── tests/                      # test unitari ed end-to-end
 ├── docs/                       # documentazione utente e sviluppatore
 └── .env                        # credenziali API, token e configurazioni locali
```

---

## 🧩 Livelli funzionali
1. **Livello 0 – Sandbox AI**: ambiente sperimentale per test e prototipi.
2. **Livello 1 – KB documentale statico**: generazione contenuti Markdown/YAML per Honkit (fork open-source di GitBook).
3. **Livello 2 – Parsing + KB vettoriale**: estrazione strutturata e indicizzazione per ricerca semantica.
4. **Livello 3 – Dashboard semantica**: interfaccia di consultazione avanzata.

---

## 🔄 Analisi del flusso degli orchestratori

### **1. pre_onboarding.py**
- **Funzioni importate**:
  - `load_config` (`pipeline/config_utils.py`) → carica e unisce parametri da `.env`, YAML in `config/` e costanti in `pipeline/constants.py`.
  - `setup_project_structure` (`pipeline/setup_utils.py`) → crea cartelle di lavoro e output.
  - `prompt_user_inputs` (`pipeline/input_utils.py`) → acquisisce slug e nome cliente.
- **Fonti dati**:
  - `.env` → credenziali API, path Google Drive, token GitHub.
  - `config/*.yaml` → parametri personalizzati.
  - `pipeline/constants.py` → valori predefiniti.
- **Output**:
  - `config/clienti/<slug>/config/config.yaml` aggiornato.
  - Struttura cartelle input/output.

### **2. onboarding_full.py**
- **Funzioni importate**:
  - `get_structured_logger` (`pipeline/logging_utils.py`) → logging centralizzato.
  - `get_drive_service`, `download_drive_pdfs_to_local` (`pipeline/drive_utils.py`) → gestione connessione e download PDF.
  - `is_safe_subpath` (`pipeline/path_utils.py`) → validazione path.
  - `convert_files_to_structured_markdown`, `generate_summary_markdown`, `generate_readme_markdown` (`pipeline/content_utils.py`) → generazione contenuti.
  - `run_gitbook_docker_preview` (`pipeline/gitbook_preview.py`) → avvio anteprima Honkit.
  - `push_output_to_github` (`pipeline/github_utils.py`) → push contenuti.
  - `get_env_var` (`pipeline/env_utils.py`) → lettura variabili ambiente.
- **Fonti dati**:
  - `output/timmy-kb-<slug>/config/<CONFIG_FILE_NAME>` → configurazione client.
  - Cartella PDF in Google Drive.
  - `.env` → token GitHub.
- **Flusso**:
  1. Caricamento configurazione cliente.
  2. Download PDF da Drive (se richiesto).
  3. Conversione PDF in Markdown strutturato.
  4. Generazione sommario e README.
  5. Preview Docker → conferma con INVIO.
  6. Push opzionale su GitHub.

---

## 🔑 File chiave
- **`pipeline/logging_utils.py`** → gestione logging.
- **`pipeline/constants.py`** → costanti e nomi file.
- **`pipeline/drive_utils.py`** → funzioni integrazione Google Drive.
- **`pipeline/content_utils.py`** → generazione contenuti.
- **`pipeline/gitbook_preview.py`** → gestione anteprima Honkit.
- **`pipeline/github_utils.py`** → interfaccia API GitHub.

---

## 📦 Funzioni Riutilizzabili

### Gestione Path e Slug (`path_utils.py`)
- **is_safe_subpath(path: Path, base: Path) -> bool** – Previene path traversal: verifica che `path` rimanga sotto `base`.  
  _Uso:_ `assert is_safe_subpath(file_path, context.base_dir)`
- **is_valid_slug(slug: str) -> bool** – Valida lo slug secondo la regex di progetto (caricata da config).  
  _Uso:_ `if not is_valid_slug(slug): raise ConfigError(...)`
- **normalize_path(path: Path) -> Path** – Normalizza e risolve il path (assoluto, senza segmenti “.”/“..”).  
  _Uso:_ `norm = normalize_path(Path(input_path))`
- **sanitize_filename(name: str, max_length: int = 100) -> str** – Ripulisce nomi file (caratteri sicuri, lunghezza massima).  
  _Uso:_ `safe = sanitize_filename(title)`

### Gestione Configurazioni (`config_utils.py`)
- **safe_write_file(file_path: Path, content: str)** – Scrittura atomica con backup (rollback sicuro).  
  _Uso:_ `safe_write_file(context.config_path, yaml_dump)`
- **update_config_with_drive_ids(context, updates: dict, logger=None)** – Merge incrementale nella `config.yaml` cliente con backup automatico.  
  _Uso:_ `update_config_with_drive_ids(ctx, {"drive_folder_id": "...", ...}, logger)`
- **write_client_config_file(context, config: dict) -> Path** – Crea/riscrive la `config.yaml` del cliente nella cartella `output/timmy-kb-<slug>/config/`.  
  _Uso:_ `path = write_client_config_file(ctx, new_cfg)`
- **get_client_config(context) -> dict** – Ritorna la configurazione cliente già validata.  
  _Uso:_ `cfg = get_client_config(ctx)`

### Gestione Variabili di Ambiente (`env_utils.py`)
- **get_env_var(key: str, default=None, required: bool = False)** – Accesso centralizzato a `.env` con validazione (solleva `ConfigError` se `required=True` e mancante).  
  _Uso:_ `token = get_env_var("GITHUB_TOKEN", default=None)`

### Gestione Logging (`logging_utils.py`)
- **get_structured_logger(name="default", log_file: Path|str|None=None, level=None, rotate=False, max_bytes=5*1024*1024, backup_count=3, context=None) -> logging.Logger** – Logger uniforme (console/file), formatter consistente e opzionale rotazione; se passi `context`, aggiunge automaticamente lo `slug` ai log.  
  _Uso:_ `logger = get_structured_logger("pre_onboarding", context=ctx)`

### Google Drive (`drive_utils.py`)
- **get_drive_service(context)** – Inizializza il client Drive usando il Service Account dal `.env`.  
  _Uso:_ `drive = get_drive_service(ctx)`
- **create_drive_folder(service, name: str, parent_id: str|None=None) -> str** – Crea cartella e ritorna l’ID.  
  _Uso:_ `client_folder_id = create_drive_folder(drive, ctx.slug, ctx.env["DRIVE_ID"])`
- **create_drive_structure_from_yaml(service, yaml_path: Path, client_folder_id: str) -> dict** – Genera la gerarchia di cartelle dal YAML (es. `cartelle_raw.yaml`) e ritorna una mappa `{nome: id}`.  
  _Uso:_ `ids = create_drive_structure_from_yaml(drive, yaml_path, client_folder_id)`
- **list_drive_files(service, parent_id: str, query: str|None=None) -> list[dict]** – Elenca file sotto una cartella (con query opzionale).  
  _Uso:_ `existing = list_drive_files(drive, client_folder_id, "name='config.yaml'")`
- **delete_drive_file(service, file_id: str)** – Elimina file su Drive per ID.  
  _Uso:_ `delete_drive_file(drive, f["id"])`
- **upload_config_to_drive_folder(service, context, parent_id: str) -> str** – Carica la `config.yaml` del cliente nella cartella target e ritorna l’ID del file.  
  _Uso:_ `cfg_id = upload_config_to_drive_folder(drive, ctx, client_folder_id)`
- **create_local_base_structure(context, yaml_path: Path)** – Crea la struttura di directory locale coerente con il mapping YAML.  
  _Uso:_ `create_local_base_structure(ctx, yaml_path)`

### GitHub (`github_utils.py`)
- **push_output_to_github(context, github_token: str|None, confirm_push: bool = True)** – Esegue il push dei Markdown generati (cartella `book/`) verso il repo/branch configurato; applica controlli di sicurezza su path `.md` prima della pubblicazione.  
  _Uso:_ `push_output_to_github(ctx, get_env_var("GITHUB_TOKEN"), confirm_push=True)`

### Honkit Preview (`gitbook_preview.py`)
- **ensure_book_json(book_dir: Path, slug: str|None=None)** – Garantisce un `book.json` minimo per Honkit (autogenerato se assente).  
  _Uso:_ `ensure_book_json(ctx.md_dir, slug=ctx.slug)`
- **ensure_package_json(book_dir: Path, slug: str|None=None)** – Garantisce un `package.json` coerente per l’esecuzione locale.  
  _Uso:_ `ensure_package_json(ctx.md_dir, slug=ctx.slug)`
- **run_gitbook_docker_preview(context, port: int = 4000, container_name: str = "honkit_preview", wait_on_exit: bool = True)** – Avvia la preview Docker+Honkit della KB; opzionalmente blocca finché non chiudi la preview.  
  _Uso:_ `run_gitbook_docker_preview(ctx, port=4000)`

### Client Context (`context.py`)
- **ClientContext.load(slug: str, logger=None, interactive: bool|None=None, **kwargs) -> ClientContext** – Carica/inizializza il contesto cliente (cartelle output, `config.yaml`, variabili `.env`).  
  _Uso:_ `ctx = ClientContext.load(slug)`
- **log_error(msg)** • **log_warning(msg)** • **set_step_status(step, status)** – Tracking omogeneo dello stato e degli eventi.  
  _Uso:_ `ctx.set_step_status("pre_onboarding", "ok")`
- **summary() -> dict** – Riepilogo finale (errori, warning, step).  
  _Uso:_ `print(ctx.summary())`
- Helper: **get_or_prompt(value, prompt, non_interactive=False, slug=None)** • **validate_slug(slug)** – Gestione input e validazione slug.  
  _Uso:_ `slug = validate_slug(slug)`

### Eccezioni Comuni (`exceptions.py`)
- Tutte ereditano da **PipelineError** e propagano contesto utile nei messaggi:  
  **DriveDownloadError**, **DriveUploadError**, **ConversionError**, **PushError**, **ConfigError**, **CleanupError**, **PreviewError**, **EnrichmentError**, **SemanticMappingError**, **PreOnboardingValidationError**.


---

## 📊 Matrice RACI – Punti HiTL Timmy-KB

| Fase / Attività | DevOps | Operatore | Revisore | Cliente |
|-----------------|--------|-----------|----------|---------|
| **1. Input iniziali** – Inserimento slug e nome cliente in `pre_onboarding` | C | R | I | A |
| **2. Popolamento cartelle Drive** – Caricamento PDF e materiali | I | C | I | R |
| **3. Conversione + Arricchimento semantico** – Esecuzione `onboarding_full` | I | R | C | I |
| **4. Preview Docker Honkit** – Verifica struttura e semantica | I | C | R | A |
| **5. Decisione Push GitHub** – Conferma pubblicazione KB | C | R | A | I |
| **6. Archiviazione log/Audit** – Registrazione decisioni umane | R | C | I | I |

**Legenda:**  
- **R** = Responsible (esegue)  
- **A** = Accountable (approva)  
- **C** = Consulted (coinvolto attivamente)  
- **I** = Informed (informato)  

> Nota: al punto 3 il Revisore è consultato in particolare per garantire la qualità semantica.

---

## ⚙️ Principi di sviluppo
- Separazione orchestrazione / logica semantica.
- Configurazione esterna.
- Logging centralizzato.
- Modularità.

---

## 📚 Collegamenti utili
- [Guida sviluppatore](developer_guide.md)
- [Guida utente](user_guide.md)
- [Regole di codifica](coding_rule.md)
