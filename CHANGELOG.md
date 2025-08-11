# 📓 Changelog – Timmy-KB

Tutte le modifiche rilevanti al progetto saranno documentate in questo file.

## **Changelog – Refactor Pipeline Timmy-KB (Sessione Agosto 2025)**

### **Stato generale**
- **`pre_onboarding.py`**: flusso completo testato, funzionante e stabile  
- **`onboarding_full.py`**: avvio funzionante ma bloccato su import legacy (`_safe_write_file`) → richiede intervento di refactor in `content_utils.py` per usare `safe_write_file` di `path_utils.py`.

---

### **Principali modifiche effettuate**
1. **ClientContext**
   - Creazione automatica struttura base cliente se inesistente
   - Copia automatica di `config/config.yaml` come template
   - Lettura variabili `.env` aggiornate (`SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `GITHUB_TOKEN`)
   - Fix path per evitare cartelle `output` annidate

2. **`path_utils.py`**
   - Aggiunte funzioni di sicurezza e sanitizzazione:
     - `is_safe_subpath` → validazione path
     - `sanitize_filename` → nomi sicuri per file/cartelle
     - `safe_write_file` → scrittura sicura (replaces `_safe_write_file`)

3. **`pre_onboarding.py`**
   - Aggiunta validazione path sicuri
   - Uso di `sanitize_filename` per Drive
   - Supporto modalità `dry_run`
   - Supporto mapping semantico globale o default
   - Backup e ripristino automatico di `config.yaml` in caso di errore
   - Flusso end-to-end testato con successo → crea cartelle locali, cartelle su Drive e aggiorna config

4. **`drive_utils.py`**
   - Sanificazione nomi file/cartelle
   - Validazione path locali
   - Logging migliorato
   - Allineamento alla funzione `create_local_base_structure` (repo)

5. **`onboarding_full.py`**
   - Aggiornamento per usare `convert_files_to_structured_markdown` di `content_utils`
   - Validazione `raw_dir` e `md_dir` con `is_safe_subpath`
   - Conversione PDF → MD dopo download
   - **Da completare:** `content_utils.py` deve eliminare dipendenza da `_safe_write_file`

6. **`content_utils.py`**
   - Analisi funzione `convert_files_to_structured_markdown` → attualmente punta a `_safe_write_file`
   - Decisione: modificare per usare `safe_write_file` di `path_utils.py`
   - Questa modifica è bloccante per il completamento del flusso `onboarding_full.py`

---

### **Stato attuale dei flussi**
- **Pre-Onboarding** ✅  
  Funzionamento confermato:  
  - Crea struttura locale cliente  
  - Crea cartelle su Drive e le popola  
  - Copia `config.yaml` e mapping  
  - Aggiorna config con ID Drive  
  - Backup automatico config

- **Onboarding Full** ⚠️  
  Funziona fino alla fase di import dei moduli  
  - Errore: `ImportError: cannot import name '_safe_write_file'`  
  - Blocco risolvibile aggiornando `content_utils.py` a usare `safe_write_file`  

---

### **Prossimi passi (prima della semantica)**
1. **Refactor `content_utils.py`** per:
   - Eliminare `_safe_write_file`
   - Usare `safe_write_file` di `path_utils`
2. Ritestare `onboarding_full.py` end-to-end
3. Push finale con pipeline robusta e coerente


## v1.9.0 – Refactor Pre-Onboarding, Gestione `.env` e Consolidamento Modalità Interattiva
**Data:** 2025-08-10  

### 🚀 Novità  
- Introdotto caricamento variabili di configurazione sensibili da `.env` tramite nuovo modulo `env_utils.py`  
- Aggiornato `ClientContext` per includere campo `env` con variabili `.env` (`GOOGLE_SERVICE_ACCOUNT`, `DRIVE_ID`, `GITHUB_TOKEN`)  
- Consolidato l’uso di `context.env` come unica fonte per i parametri di integrazione esterna (Drive, GitHub)  
- Integrazione di parametri `.env` in `get_drive_service()` rimuovendo la dipendenza dal `config.yaml`  
- Adattamento di `pre_onboarding.py` per:  
  - Caricare il file YAML di struttura locale da percorso dinamico (`local_structure_file` in `config.yaml`)  
  - Supportare modalità interattiva completa se non in fase di test  
  - Gestire creazione `config.yaml` iniziale senza dover caricare un contesto incompleto  

### 🔧 Modifiche  
- **`ClientContext`**:  
  - Aggiunto caricamento variabili `.env` in `load()`  
  - Uniformata la gestione di `config_path` come riferimento al file di configurazione  
  - Eliminata distinzione `config_file`/`config_dir` per semplificare il flusso  
- **`pre_onboarding.py`**:  
  - Aggiornata chiamata a `create_local_base_structure()` per usare `yaml_path` specificato in configurazione  
  - Copia del template `config.yaml` e `semantic_mapping.yaml` nella cartella del cliente  
  - Gestione interattiva di `slug` e `client_name` con creazione diretta del file `config.yaml`  
  - Allineamento chiamate a `upload_config_to_drive_folder()` e `create_drive_structure_from_yaml()`  
- **`drive_utils.py`**:  
  - Aggiornato `get_drive_service()` per leggere credenziali da `context.env["GOOGLE_SERVICE_ACCOUNT"]`  
  - Uniformata firma di `upload_config_to_drive_folder()` per accettare `ClientContext`  
- **`logging_utils.py`**:  
  - Rimosso potenziale problema di circular import spostando l’uso del logger di contesto in fase runtime  

### 🐛 Bug Fix  
- Risolto `AttributeError: 'ClientContext' object has no attribute 'config_file'` in pre-onboarding  
- Corretta mancata individuazione del file `cartelle_raw.yaml` nella creazione della struttura locale  
- Fix per caricamento interattivo di slug/nome cliente senza forzare `ClientContext.load()` prima della creazione del config  

### 📌 Stato attuale  
- Pre-onboarding ora crea correttamente struttura locale e copia file di configurazione  
- Gestione `.env` implementata ma connessione a Google Drive ancora bloccata da parametri non caricati correttamente in `get_drive_service()`  
- Prossimo step: completare l’integrazione di `env_utils.py` e validare end-to-end la pipeline con modalità interattiva HiTL e CLI skip test-ready  


## [2025-08-10] fix/refactor: stabilizzazione onboarding_full.py e github_utils.py con gestione esplicita di settings e slug

### 🛠️ Modifiche a `onboarding_full.py`
- Rivista l’inizializzazione di `settings` tramite `get_settings_for_slug(slug)` e mantenuta coerente per tutto il flusso.
- Passaggio esplicito di `settings` e `md_dir_path` a `push_output_to_github` per evitare errori di slug mancante.
- Aggiornato il passaggio a `run_gitbook_docker_preview` con `slug=slug` per allineamento firma funzione.
- Preservata logica esistente, evitando modifiche superflue e mantenendo compatibilità batch/interattiva con `--auto-push` e `--skip-preview`.
- Confermato il caricamento di `client_config` a inizio run con validazione di `drive_folder_id`.

### 🛠️ Modifiche a `github_utils.py`
- Refactor di `push_output_to_github` per richiedere sempre `settings` come parametro obbligatorio.
- Nome repository calcolato come `GITHUB_REPO` da settings o `timmy-kb-<slug>` se non presente.
- Fallback automatico a `GITHUB_TOKEN` da variabile d’ambiente.
- Validazione `output_path` con `_validate_path_in_base_dir` per garantire che sia all’interno della base del cliente.
- Creazione repo GitHub solo se assente; push forzato su `master` dei soli file `.md` utili.
- Gestione sicura della cartella temporanea `tmp_repo_push` (rimozione prima e dopo il push).

### 🛠️ Modifiche correlate e verifiche
- Controllata coerenza di `_resolve_settings` e gestione slug anche in `gitbook_preview.py` (nessuna modifica invasiva, solo verifica).
- Confermata compatibilità con il nuovo modello `Settings` in `config_utils.py` che ora supporta lo slug come campo nativo.
- Testata esecuzione end-to-end della pipeline di onboarding con `--auto-push` attivo.

### ✅ Risultati
- Esecuzione completa di onboarding con download PDF, conversione, arricchimento semantico, generazione `SUMMARY.md` e `README.md`, preview GitBook e push GitHub senza salti di step.
- Eliminati errori e warning legati a slug mancante in fasi critiche.
- Pipeline multi-cliente stabile e pronta per il deploy GitHub in produzione.


## [2025-08-09] fix/refactor: stabilizzazione onboarding_full.py e allineamento config_utils.py per gestione slug

### 🛠️ Modifiche a `onboarding_full.py`
- Mantenuta struttura e logica originale, intervenendo **solo** per garantire compatibilità con gestione multi-cliente.
- Aggiunta impostazione esplicita `settings.slug = slug` subito dopo l’inizializzazione di `settings` tramite `get_settings_for_slug()`.
- Confermata la ricerca PDF in `raw/` con scan ricorsivo (`rglob`) per supportare sottocartelle, evitando falsi negativi.
- Preservata la pausa interattiva dopo la preview Docker e prima del push su GitHub, mantenendo coerenza batch/manuale.
- Nessuna modifica superflua: invariati import, naming e flusso operativo.

### 🛠️ Modifiche a `config_utils.py`
- Aggiunto campo opzionale `slug: Optional[str] = None` al modello `Settings` (Pydantic) per supporto nativo allo slug cliente.
- Sostituiti tutti i riferimenti a `self.SLUG` con `self.slug` per evitare `AttributeError` e allineare naming.
- Aggiornati messaggi di errore e log in `check_critico` per usare il campo corretto.
- Corrette proprietà `output_dir` e `logs_path` per usare `self.slug`.
- Aggiornata `get_settings_for_slug()` per passare `slug` minuscolo al costruttore di `Settings`, eliminando l’errore `extra_forbidden` di Pydantic v2.

### ✅ Risultati
- Onboarding completo ora esegue senza crash in presenza di slug cliente.
- Gestione slug integrata in `Settings`, eliminando workaround e garantendo coerenza tra orchestratori.
- Compatibilità confermata con funzioni `push_output_to_github` e `run_gitbook_docker_preview`.
- Struttura repo e pipeline allineata, pronta per test di deploy GitHub end-to-end.


## **Interventi – Agosto 2025 (commit intermedio, revisione onboarding_full.py e correlati)**

### **Modifiche principali**
- **`onboarding_full.py`**
  - Corretto passaggio dei parametri a funzioni esterne (`run_gitbook_docker_preview`, `push_output_to_github`) in modo coerente con la loro firma aggiornata.
  - Introdotto passaggio esplicito dell’oggetto `settings` per evitare errori di tipo `get_settings_for_slug() missing 1 required positional argument: 'slug'`.
  - Passato `md_dir_path` esplicito a `push_output_to_github` per eliminare ambiguità e rendere più chiaro il flusso.
  - Nessuna modifica superflua: mantenuta logica esistente e struttura del file invariata.

### **File correlati analizzati**
- **`gitbook_preview.py`**
  - Rivisto `_resolve_settings` per futura compatibilità con passaggio esplicito di `settings`.
  - Confermata validazione dei percorsi e gestione sicura dei file `book.json` e `package.json`.

- **`github_utils.py`**
  - Verificata compatibilità con passaggio esplicito di `settings` e `md_dir_path` da `onboarding_full.py`.
  - Nessun refactoring non necessario applicato, mantenuta logica di deploy GitHub invariata.

- **`semantic_extractor.py`**
  - Confermato utilizzo del parametro `mapping_source` per permettere passaggio diretto del mapping da `onboarding_full.py` senza ricaricarlo da file.
  - Evidenziata necessità di gestire casi in cui lo `slug` non sia presente né nel mapping né in `settings` (problema ancora aperto).

### **Note operative**
- Commit volutamente **intermedio**: restano da affrontare:
  - Errori di “slug mancante” in `semantic_extractor.py`.
  - Verifica end-to-end della procedura di push GitHub.
  - Allineamento definitivo di `_resolve_settings` in tutti i moduli per eliminare chiamate errate a `get_settings_for_slug`.


## [2025-08-09] feat+fix/pre_onboarding: struttura locale e Drive da YAML

### ✨ Nuove funzioni
- `utils.py`: aggiunta `create_local_base_structure()` per generare la struttura locale cliente con naming `timmy-kb-<slug>` e sottocartelle `raw` da `config/cartelle_raw.yaml`.
- `drive_utils.py`: aggiunta `create_drive_structure_from_yaml()` per generare l’intera struttura su Drive da `cartelle_raw.yaml` in modo ricorsivo.

### 🛠 Refactor `pre_onboarding.py`
- Corretto naming cartella cliente in locale.
- Creazione sottocartelle `raw` in locale da YAML.
- Creazione struttura top-level su Drive leggendo da `cartelle_raw.yaml` (`raw`, `contrattualistica`, ecc.) con sottocartelle relative.
- `config.yaml` caricato direttamente nella cartella cliente su Drive.
- Mantenuta la logica originale per evitare regressioni nella pipeline.

### ✅ Obiettivi
- Allineamento struttura locale e remota alle specifiche YAML.
- Maggiore coerenza nella gestione di `config.yaml`.
- Modifiche minime per preservare stabilità e compatibilità.


## [2025-08-08] fix/refactor: stabilizzazione pre-onboarding e gestione cartelle Drive

### 🛠️ Refactor `drive_utils.py`
- Rimosso parametro obbligatorio `settings_instance` da `create_drive_folder`: ora accetta solo `service`, `name` e `parent_id`.
- Gestione `driveId` limitata alle query (`files().list`), evitando errori API in `files().create`.
- Log migliorati con indicazione chiara di nome cartella, ID e parent su Drive.

### 🔄 Aggiornamenti `pre_onboarding.py`
- Corretto passaggio parametri a `create_drive_folder` e `upload_config_to_drive_folder` per compatibilità API.
- Implementata creazione automatica su Drive della struttura `raw/`, `book/`, `config/` accanto alla cartella cliente.
- Backup automatico `.bak` del `config.yaml` locale dopo aggiornamento con `drive_folder_id`.

### 🐞 Fix limiti Google Drive
- Gestito errore 403 `storageQuotaExceeded` con indicazione chiara nel log: upload supportato solo su Shared Drive.
- Allineati riferimenti da `DRIVE_ROOT_ID` a `DRIVE_ID` come definito in `.env`.

### ✅ Risultati
- Pre-onboarding ora crea struttura cartelle sia in locale che su Drive senza errori di parametri API.
- `config.yaml` aggiornato e sincronizzato con ID cartella cliente su Drive.
- Pipeline pronta per test di onboarding completo e push GitHub.


## [2025-08-08] refactor: allineamento orchestratori, fix push GitHub e stabilizzazione pre-onboarding/onboarding

### 🔄 Allineamento `pre_onboarding.py` con repo
- Ripristinata la versione aggiornata dal repository come base, applicando **solo le modifiche necessarie**:
  - Uso corretto di `create_drive_folder` con 3 argomenti per evitare errori `unexpected keyword argument driveId`.
  - Conservata l’inizializzazione di `settings` per lo `slug` corrente tramite `get_settings_for_slug`.
  - Confermata la generazione completa della struttura cartelle su Drive a partire da `cartelle_raw.yaml`.

### 🛠️ Correzioni `onboarding_full.py`
- Fix caricamento config cliente: ora `load_client_config` cerca il file in `output/timmy-kb-<slug>/config/config.yaml` senza duplicazioni di path.
- Aggiornato il blocco finale di push:
  - Passa l’oggetto `settings` alla funzione `push_output_to_github` per mantenere coerenza multi-cliente.
  - Gestione interattiva (`y/N`) preservata, con possibilità di `--auto-push` batch.
- Validata la presenza di `drive_folder_id` e blocco esplicito se mancante, evitando download PDF fuori contesto cliente.

### 🚀 Refactor `github_utils.py`
- Funzione `push_output_to_github` aggiornata per ricevere **esplicitamente** `settings` e path opzionale `md_dir_path`.
- Aggiunto fallback a `os.getenv("GITHUB_TOKEN")` per garantire compatibilità con `.env`.
- Fix mancato import di `os` che causava `NameError` in fase di push.
- Confermata logica di creazione repo solo se non esiste, push forzato su `master` e commit esclusivo dei `.md` utili.

### 📂 Configurazione e coerenza path
- Allineato valore `local_temp_config_path` a `config/config.yaml` nei file `config.yaml` generati, evitando riferimenti errati a `temp_config/config.yaml`.
- Validato che la pipeline scarichi i PDF nella cartella `raw_dir` del cliente (`output/timmy-kb-<slug>/raw`), senza percorsi ambigui.

### ✅ Risultati
- Pipeline `pre_onboarding` e `onboarding_full` ora eseguibili end-to-end senza errori.
- Creazione cartelle Drive, download PDF, conversione, arricchimento semantico, preview GitBook e push GitHub completati correttamente.
- Pronto per ulteriori ottimizzazioni ma con stato stabile e sincronizzato con il repository.


## [X.Y.Z] - 2025-08-06

### Modifiche principali

- Refactoring completo di `config_utils.py`: rimosso singleton globale `settings`, introdotto utilizzo esclusivo della factory `get_settings_for_slug(slug)` per tutte le pipeline per-client.
- Aggiornamento orchestratori (`pre_onboarding.py`, `onboarding_full.py`) per compatibilità con la nuova gestione multi-client di `settings`.
- Refactoring funzioni/utility per ricevere `settings` come parametro, evitando riferimenti globali.
- Fix bug critico su generazione errata di cartelle/slug nelle pipeline onboarding (root path e raw path).
- Warning e validazioni migliorate: errore esplicito se lo slug non viene passato correttamente.
- Documentazione aggiornata nei moduli per chiarire il flusso e l'utilizzo corretto di `settings`.

### Effetti collaterali

- **ATTENZIONE**: Qualsiasi modulo che usava `from pipeline.config_utils import settings` DEVE ora istanziare `Settings()` direttamente *oppure* ricevere un oggetto settings come argomento.
- Pipeline ora multi-client, pronta per esecuzioni concorrenti e deploy più sicuro.


## [2025-08-08] refactor(wip): gestione drive_folder_id e compliance download PDF cliente

### 🗂️ Gestione avanzata `drive_folder_id` (multi-cliente)
- Ora la pipeline **carica e utilizza dinamicamente** il campo `drive_folder_id` dal config YAML del cliente (`output/timmy-kb-<slug>/config/config.yaml`), sia in orchestrazione che nelle utility Google Drive.
- **Blocco rigoroso** se `drive_folder_id` non è presente o non valido: il download dei PDF *fallisce* senza fallback sulla root del Drive condiviso (compliance NeXT).
- Funzione `download_drive_pdfs_to_local` aggiornata: riceve ora `drive_folder_id` (cartella cliente) e `DRIVE_ID` (shared drive) come parametri espliciti, evitando ogni ambiguità e bug multi-cliente.
- Logging chiaro sull’identità delle cartelle Drive coinvolte in ogni fase di download/upload.

### 🔒 Error handling, naming & coerenza config
- `drive_utils.py` ora rifiuta ogni operazione se `drive_folder_id` non è presente o coerente (pre-onboarding incompleto/config corrotto).
- Allineata la terminologia **Drive** in tutto il codice (`drive_folder_id` = cartella cliente, `DRIVE_ID` = shared drive root da .env/config).
- Docstring e logging rivisti per chiarezza operativa (chi fa cosa e su quale Drive/cliente).

### 🛠️ Orchestratori allineati
- Orchestratore `onboarding_full.py` ora carica esplicitamente il config cliente a inizio run, estraendo e passando `drive_folder_id` alle funzioni di download PDF.
- Tutte le funzioni di download/upload su Drive sono ora *parametriche* e batch-friendly (no hardcoded settings).

---

**NOTE:**  
Questo refactoring è **intermedio**: ora la pipeline è pronta per multi-cliente, nessun rischio di download “incrociati” o di corruzione tra progetti.  
Prossimi passi: refactor upload e utility drive avanzate, estensione logging e test coverage, uniformità semantica.


## [2025-08-06] - Refactor e miglioramenti strutturali

- **Nuova policy di output `book/`:**
  - Ora ogni cartella in `raw/` viene aggregata in **un unico file `.md`** (nome = nome cartella), eliminando la generazione di un file `.md` per ogni PDF.
  - La cartella `book/` contiene solo i file `.md` aggregati per cartella più i file core (`README.md`, `SUMMARY.md`).

- **Funzione di conversione aggiornata (`content_utils.py`):**
  - Implementata nuova funzione che aggrega i PDF di ciascuna cartella in un unico file `.md`.
  - Struttura di output semplificata e pulita.

- **Push su GitHub snellito (`github_utils.py`):**
  - Ora vengono committati e pushati **solo** i file `.md` realmente utili, senza più copiare cartelle o file temporanei non voluti.
  - Possibilità di estendere facilmente a immagini/asset (commentato nello snippet).

- **Chiarezza e compliance alle regole aziendali:**
  - Output di pipeline sempre pulito e tracciabile.
  - Nessun side-effect da log, temporanei, raw, backup, test, ecc.
  - Massima chiarezza e atomicità dei commit.

---

**NOTE:**  
Questi cambiamenti migliorano la governance della pipeline, riducono il rumore nel repository, facilitano review e rollback, e garantiscono che solo gli artefatti finali e rilevanti vengano versionati.



## [2025-08-07] refactor: docstring, coerenza CLI e compliance architetturale pipeline

### 📖 Miglioramento docstring & commenti
- Aggiunte docstring di **modulo, funzione e proprietà** per tutti i file della cartella `src/pipeline/`:
    - Descrizione chiara delle responsabilità, dei parametri e dei ritorni.
    - Uniformato lo stile alle convenzioni PEP257/Napoleon.

### 🧩 Refactor import, logging e naming
- Ordinati tutti gli import secondo PEP8 (standard, third-party, local).
- Verificato che **ogni modulo** usi il logger strutturato locale tramite `get_structured_logger`.
- Eliminato ogni uso di `print()` fuori da CLI o test.
- Tutti i nomi di funzioni, classi e variabili uniformati a `snake_case`/`PascalCase` come da policy.

### 🏗️ Uniformità orchestratori e CLI
- Tutte le funzioni principali (`onboarding_main`, `preonboarding_main` ecc.) ora dotate di docstring e parametri espliciti.
- Parametri CLI documentati e fallback input sempre gestito per modalità batch/manuale.

### 🔒 Sicurezza e validazione
- Rafforzati i controlli sulle funzioni di pulizia (`safe_clean_dir`, `cleanup_output_folder`) per prevenire rischi sui path critici.
- Validazione slug e ambiente preonboarding con logging dettagliato ed eccezioni dedicate.

### 🛠️ Best practice di struttura pipeline
- Assicurata **separazione netta** tra orchestrazione tecnica (`pipeline/`) e logica semantica (`semantic/`).
- Configurazione e segreti ora centralizzati in `TimmyConfig`, gestione YAML/property unificata.

### ⚙️ Uniformità CLI e batch
- Orchestratori e utility accettano tutti i parametri via CLI (`argparse`), modalità batch/interattiva sempre distinguibile tramite flag (`--no-interactive`, `--auto-push`, ecc).

---

> Ora l’intera pipeline tecnica è documentata, pulita, conforme alle policy aziendali e pronta per essere estesa sul fronte semantico/AI e per review tecnica avanzata.


## [2025-08-06] refactor: compliance logging, error handling & pulizia moduli inutilizzati

### ♻️ Refactor orchestratori & error handling
- Refactor globale di tutti i file orchestratori (`pre_onboarding.py`, `onboarding_full.py`):
    - **Gestione uniforme degli errori**: ora tutti gli errori bloccanti vengono loggati e rilanciati tramite eccezioni custom (`PipelineError`, `PreOnboardingValidationError`), con `sys.exit(1)` solo a livello di entrypoint/CLI.
    - **Eliminazione di tutti i print() e exit(1)** sparsi nei moduli di validazione/config, sostituiti da logging strutturato e custom exceptions.
    - **Gestione errori esplicita e trasparente**: logging sempre presente prima di ogni terminazione forzata, nessun errore silenzioso.

### 🏗️ Architettura e dipendenze
- Uniformato l’uso del logger centralizzato tramite factory (`get_structured_logger`) in **tutti i moduli** (inclusi moduli semantic).
- **Rimosso ogni duplicazione di funzione**: ora `load_semantic_mapping` viene importato unicamente da `semantic_mapping.py`, eliminando la duplicazione in `semantic_extractor.py`.

### 🧹 Pulizia moduli inutilizzati
- **Eliminato il modulo `file2md_utils.py`**: tutte le funzioni di conversione e arricchimento PDF→Markdown sono oggi implementate e richiamate in `content_utils.py` e pipeline principali.
- Nessuna funzione chiave persa: tutte le logiche di batch, frontmatter, tagging, enrichment sono presenti e attive nei moduli di orchestrazione.

### 📑 Chiarezza documentazione e policy
- Aggiornata la documentazione interna: chiarito dove avviene la conversione PDF→Markdown e l’enrichment semantico.
- Nota di deprecazione: *nessun modulo "legacy" attivo – tutti i flussi sono ora conformi alle regole NeXT, con logging e gestione errori centralizzati.*

---

> Refactor completato: il progetto ora rispetta pienamente le policy aziendali su logging, errori e modularità, senza più moduli dormienti o duplicati. Pronto per CI/CD e review tecnica avanzata.



## [2025-08-05] refactor: standardizzazione batch/manuale & revisione orchestratori e test

### ♻️ Refactor globale orchestratori e pipeline
- Uniformato il comportamento di tutti i file orchestratori (`pre_onboarding.py`, `onboarding.py` e pipeline root):
    - Ora supportano CLI parametrica (`--slug`, `--no-interactive`, `--auto-push`, `--skip-preview`)
    - Input interattivo solo in esecuzione manuale; **mai in batch o CI**
    - Logging strutturato e centralizzato, eliminati tutti i print residui
    - Uscita con exit code gestito in caso di errore bloccante
- Refactor della gestione del logging in tutti i moduli: uso esclusivo di logger dedicati e fallback robusto su console

### 🧪 Refactor e adeguamento test
- Aggiornate tutte le fixture e teardown dei test: ora compatibili sia con esecuzione singola/manuale che batch (pytest globale/CI)
- **Nuova logica `BATCH_TEST=1`**:
    - Se impostata, cleanup automatico e nessun input nei test
    - In assenza, conferma manuale e print di stato per debug locale
- Tutti i print di stato e debug nei test convertiti in logger (`logger.info`, `logger.debug`)
- Cleanup e teardown dei test ora sempre batch-friendly e idempotenti
- Aggiornata la sezione *Testing Rules* in `coding_rule.md` secondo le nuove policy batch/manuale

### 📜 Policy e best practice
- Inserite e chiarite in `coding_rule.md` le nuove regole di testing batch/manuale:
    - Test batch-friendly obbligatori, mai input() o print() in CI
    - Comportamento manuale consentito solo su test singoli
    - Cleanup automatico o confermabile solo in modalità manuale
- Introdotto uso della variabile `BATCH_TEST=1` per discriminare tra batch/manuale in modo standard e cross-piattaforma

### 🐞 Fixed
- Correzione definitiva di ogni potenziale blocco su input nei test e negli orchestratori
- Eliminati gli ultimi workaround su cleanup container Docker e teardown repo GitHub nei test

---

> Tutti i moduli e i test sono ora perfettamente idempotenti, batch-friendly e pienamente conformi alle regole NeXT, pronti per CI/CD e sviluppo collaborativo.


---
## [2025-08-04] refactor: fixbug e definizione test

### ♻️ Refactor iniziale
- Corretto bug critico nella funzione `drive_utils.download_drive_pdfs_to_local` relativo al mapping `folder_id -> nome tematico`
- Allineati i path dei file generati (`RAW_DIR`, `BOOK_DIR`, `DUMMY_YAML`) con le convenzioni del progetto
- Rimozione riferimenti obsoleti alla cartella `filetest/`, sostituita con `output/timmy-kb-dummy/raw/`
- Applicate migliorie minori alla struttura di logging e messaggi CLI

### ✅ Aggiunta e sistemazione test
- Creato file `tests/test_drive_utils.py` per testare tutte le funzioni chiave di `drive_utils`
- Fix test `test_find_folder` con allineamento parametri corretti `drive_id` e `drive_folder_id`
- Inseriti print di debug temporanei per il tracciamento del comportamento in ambiente condiviso
- Documentato limite strutturale dei service account nei test Google Drive (errore 403 quota)


## [1.0.0] – 2025-08-04

### 🚀 Added
- Prima versione pubblica **1.0** della pipeline Timmy-KB.
- Separazione netta tra moduli di pipeline (`src/pipeline/`) e orchestrazione (file root `src/`).
- Introduzione della struttura dedicata per moduli semantici (`src/semantic/`), pronta per l’implementazione delle funzioni semantiche future.
- Logging centralizzato e configurazione unificata via `.env` e moduli di utilità.
- Cartella `tools/` con strumenti di supporto: pulizia repo, generazione dummy KB, refactor automatico, validazione struttura.
- Sistema di test end-to-end e test di unità sui principali moduli della pipeline.
- Documentazione aggiornata (`README.md`), nuova roadmap per estensione semantica.
- Regole di coding (`coding_rule.md`) e manifesto tecnico (`manifesto_tecnico.md`) allegati e integrati nei processi di sviluppo.

### 🛠️ Changed
- Refactoring architetturale: la pipeline è ora completamente idempotente, testabile e pronta per l’estensione semantica.
- Orchestrazione centralizzata da file root, nessun accoppiamento diretto tra pipeline e semantica.

### 🐞 Fixed
- Vari bug relativi a conversione file PDF→Markdown e gestione directory temporanee.
- Logging migliorato e gestione errori più chiara durante l’onboarding.

---

## [Unreleased]

- Avvio sviluppo e integrazione delle funzioni semantiche: estrazione, normalizzazione, mapping concetti.
- Estensione della copertura test a tutti i nuovi moduli semantici.
- Miglioramenti su explainability, documentazione e supporto onboarding clienti.

---

> Questo file segue il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e semantica delle versioni [SemVer](https://semver.org/lang/it/).
