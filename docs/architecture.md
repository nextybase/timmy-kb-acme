# Architettura Tecnica – Timmy-KB

Questo documento descrive in dettaglio l’architettura di **Timmy-KB**, con un focus particolare sul flusso degli orchestratori, le funzioni importate, le variabili passate, le fonti dati utilizzate e il ruolo dei file chiave, basandosi sul codice effettivo presente in `src/onboarding_full.py`.

---

## 📂 Struttura del repository
```
root/
 ├── src/
 │    ├── pipeline/     # Orchestrazione e logica di esecuzione
 │    ├── semantic/     # Parsing, tagging, mapping, validazione e arricchimento semantico
 │    └── tools/        # Utility, validatori, refactoring
 ├── config/            # Configurazioni YAML
 ├── output/            # Output Markdown/YAML generati
 ├── tests/             # Test end-to-end e unitari
 ├── docs/              # Documentazione utente e sviluppatore
```

---

## 🧩 Livelli funzionali
1. **Livello 0 – Sandbox AI**: ambiente sperimentale per test e prototipi.
2. **Livello 1 – KB documentale statico**: generazione contenuti Markdown/YAML per GitBook o Honkit.
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
  - `config/config.yaml` aggiornato.
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

## ⚙️ Principi di sviluppo
- Separazione orchestrazione / logica semantica.
- Configurazione esterna.
- Logging centralizzato.
- Modularità.

---

## 📚 Collegamenti utili
- [Guida sviluppatore](developer_guide.md)
- [Guida utente](user_guide.md)
- [Regole di codifica](coding_rules.md)

