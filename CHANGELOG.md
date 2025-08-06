# 📓 Changelog – Timmy-KB

Tutte le modifiche rilevanti al progetto saranno documentate in questo file.

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
