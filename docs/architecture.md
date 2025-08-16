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
- **is_safe_subpath(path: Path, base: Path) -> bool** – Verifica anti-path traversal.  
- **is_valid_slug(slug: str) -> bool** – Validazione slug via regex configurabile.  
- **normalize_path(path: Path) -> Path** – Normalizzazione e risoluzione path.  
- **sanitize_filename(name: str, max_length=100) -> str** – Pulizia nomi file sicura.  

### Gestione Configurazioni (`config_utils.py`)
- **safe_write_file(file_path: Path, content: str)** – Scrittura sicura con backup.  
- **update_config_with_drive_ids(context, updates: dict, logger=None)** – Aggiornamento parziale config YAML con backup.  
- **write_client_config_file(context, config: dict) -> Path** – Salvataggio config cliente con backup.  
- **get_client_config(context) -> dict** – Lettura config cliente.  

### Gestione Variabili di Ambiente (`env_utils.py`)
- **get_env_var(key: str, default=None, required=False)** – Accesso centralizzato a variabili ambiente con validazione.  

### Gestione Logging (`logging_utils.py`)
- **get_structured_logger(name="default", log_file=None, level=None, rotate=False, ...)** – Logger uniforme console/file.  

### Google Drive (`drive_utils.py`)
- **drive_api_call(func, *args, **kwargs)** – Retry generico API Drive.  
- **create_drive_folder(service, name, parent_id=None) -> str** – Creazione cartella Drive sicura.  
- **list_drive_files(drive_service, parent_id, query=None)** – Elenco file cartella Drive.  
- **delete_drive_file(drive_service, file_id)** – Eliminazione file Drive.  

### GitHub (`github_utils.py`)
- **push_output_to_github(context, github_token, confirm_push=True)** – Push cartella Markdown su repo GitHub (riusabile se parametrizzato).  

### Honkit Preview (`gitbook_preview.py`)
- **ensure_book_json(book_dir, slug=None)** – Generazione file base `book.json`.  
- **ensure_package_json(book_dir, slug=None)** – Generazione file base `package.json`.  
- **run_gitbook_docker_preview(context, port=4000, container_name="honkit_preview", wait_on_exit=True)** – Avvio preview Docker (riusabile se modularizzato).  

### Client Context (`context.py`)
- **ClientContext.load(slug, ...)** – Creazione/validazione contesto cliente.  
- **log_error(msg)**, **log_warning(msg)**, **set_step_status(step, status)** – Tracking stato esecuzione.  
- **summary()** – Resoconto finale esecuzione.  
- Funzioni helper: **get_or_prompt**, **validate_slug**.  

### Eccezioni Comuni (`exceptions.py`)
- Tutte ereditano da **PipelineError**:
  - **DriveDownloadError**
  - **DriveUploadError**
  - **ConversionError**
  - **PushError**
  - **ConfigError**
  - **CleanupError**
  - **PreviewError**
  - **EnrichmentError**
  - **SemanticMappingError**
  - **PreOnboardingValidationError**

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
