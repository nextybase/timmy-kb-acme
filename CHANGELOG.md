# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

## [1.1.0] — 2025-08-19

### Added
- **Redazione log centralizzata (toggle)**: `is_log_redaction_enabled(context)` ora usata dagli orchestratori per propagare `redact_logs` ai moduli sensibili (Drive, Preview, GitHub); documentazione aggiornata.  
  File: `src/onboarding_full.py`, `src/pipeline/env_utils.py`, `docs/developer_guide.md`, `docs/policy_push.md`.

### Changed
- **Push GitHub → incrementale di default (no force)**: clone in working dir temporanea **dentro** `output/timmy-kb-<slug>`, `pull --rebase`, commit solo se ci sono diff, `push` senza `--force` con **un retry** su rifiuto non-fast-forward. Token veicolato via `GIT_HTTP_EXTRAHEADER`.  
  File: `src/pipeline/github_utils.py`.  
  Policy: se conflitti persistono, la funzione solleva `PipelineError` con istruzioni operative (branch dedicato/PR o force controllato lato orchestratore).

- **Validazione porta preview**: in `onboarding_full.py` la `--port` deve essere `1..65535`; messaggio di errore tipizzato (`ConfigError`).  
  File: `src/onboarding_full.py`.

- **Validazione slug**: rimozione duplicazioni; `context.validate_slug` delega a `path_utils.validate_slug` (che alza `InvalidSlug`) e mappa a `ConfigError`.  
  File: `src/pipeline/context.py`, `src/pipeline/path_utils.py`.

- **Path-safety**: `is_safe_subpath` semplificata con `Path.is_relative_to(...)` (chiarezza e robustezza sugli edge case).  
  File: `src/pipeline/path_utils.py`.

- **Hardening contenuti Markdown**: `content_utils` usa eccezioni di dominio (`InputDirectoryMissing`) per directory mancanti/non valide e rafforza i guard-rail di path-safety.  
  File: `src/pipeline/content_utils.py`.

- **.env & helper**: `env_utils` carica automaticamente `.env`, mantiene `get_env_var(...)` per retro-compatibilità ed espone `require_env/get_bool/get_int/redact_secrets`.  
  File: `src/pipeline/env_utils.py`.

- **Docs**: guida sviluppatore e policy di push aggiornate per riflettere il push incrementale, il toggle di redazione e i ruoli tra orchestratori e moduli.  
  File: `docs/developer_guide.md`, `docs/policy_push.md`.

### Fixed
- Messaggi e metadati di log più coerenti/strutturati negli orchestratori; stop del container di preview in `finally` preservato.  
  File: `src/onboarding_full.py`.

### Migration Notes
- **Comportamento di push modificato**: il default non sovrascrive più la storia remota. Se dipendevi dal force-push, usa un branch dedicato e apri PR, oppure abilita il force a livello di orchestratore in maniera esplicita e governata (vedi `docs/policy_push.md`).

### Compatibility
- Nessun breaking change su CLI o firme pubbliche. Modifica di policy **safe-by-default** sul push.


## [1.0.4] — 2025-08-19
### Added
- Introdotto file `coding_rules.py` con regole operative unificate per la scrittura e la manutenzione della pipeline.
- Linee guida su linguaggio, tipizzazione, naming e ordine degli import, con supporto a Ruff/Black/Mypy.
- Tassonomia centralizzata di eccezioni (`exceptions.py`) con mapping deterministico a `EXIT_CODES`.
- Logging strutturato tramite `logging_utils` con supporto a `redact_logs` e metadati contestuali (`slug`, `file_path`, `step`).
- Policy di sicurezza: validazione percorsi con `is_safe_subpath`, scritture atomiche, gestione sicura delle variabili tramite `env_utils`.
- Gestione standardizzata di subprocess, Docker preview e push GitHub con ruoli chiari tra orchestratori e moduli.
- Retry con backoff esponenziale e download idempotente per Google Drive.
- Regole di deprecazione e compatibilità retroattiva per CLI e moduli.
- Test minimi manuali documentati per `pre_onboarding`, `onboarding_full` e push GitHub.
- Linee guida per la qualità del codice e best practice di manutenibilità.

### Changed
- Rivista e uniformata la struttura di `coding_rules.py`: consolidamento in sezioni chiare (linguaggio, orchestratori vs moduli, logging, I/O, configurazioni, rete, deprecazione, test).
- Logging ripulito da `print()` ed eccezioni generiche, sostituiti da logger strutturati e tassonomia dedicata.
- Regole di preview Docker: ora sempre **detached**, con stop automatico demandato agli orchestratori.
- Uniformata la gestione di variabili e config YAML tramite `env_utils` e cache slug centralizzata.
- Aggiornati esempi di codice per riflettere i nuovi standard.

### Fixed
- Eliminati casi di `input()` o `sys.exit()` all’interno dei moduli: ora confinati negli orchestratori.
- Sistemata gestione di eccezioni non tipizzate in moduli critici (preview, push, drive).
- Migliorata robustezza della validazione slug e pulizia della cache dopo modifiche.
- Corretta gestione dei log con percorsi assenti o skip non critici (ora marcati DEBUG, non WARNING).

### Deprecated
- Flag `--skip-push` marcato come deprecato in favore di `--no-push` (verrà rimosso in una futura MINOR).
- Alias e vecchie firme dei moduli mantenuti per retrocompatibilità fino alla prossima release MINOR.


## [1.0.4] - 2025-08-18
### Changed
- Aggiornato `gitbook_preview.py`: anteprima HonKit sempre in modalità *detached* con auto-stop del container al termine della pipeline. Aggiunta opzione di redazione log.
- Rafforzata la gestione delle variabili d’ambiente in `env_utils.py`: `require_env` più rigoroso, helper `get_bool`/`get_int`, sistema di redazione segreti abilitabile via `LOG_REDACTION`.
- Migliorata la validazione slug in `path_utils.py`: regex caricata da `config.yaml` con caching e funzione di reset (`clear_slug_regex_cache`).
- Logging centralizzato: ora tutti i moduli usano `logging_utils.py` con rotazione e formattazione uniforme.
- `content_utils.py`: generazione consolidata di `README.md` e `SUMMARY.md` con validazioni più robuste.
- `github_utils.py`: push `.md` da `book/` con risoluzione branch da env e logging redatto se abilitato.
- `drive_utils.py`: download BFS ricorsivo da Drive con idempotenza e metriche di retry.

### Added
- Nuovo modulo `cleanup_utils.py` per la rimozione sicura di artefatti locali post-push legacy.
- Nuovo modulo `env_utils.py` per la gestione delle `.env` e helper centralizzati.

### Fixed
- Eliminata possibilità di preview interattiva bloccante in `gitbook_preview.py`.
- Uniformata la gestione degli slug “soft” nei moduli di path.


## [1.0.4] - 2025-08-18

### Changed
- **Validazione slug spostata negli orchestratori**: rimossa ogni interattività dai moduli.
  - `ClientContext.load(...)` ora solleva sempre `ConfigError` in caso di slug mancante/non valido (nessun `input()` nel modulo).
  - `pre_onboarding.py` e `onboarding_full.py`: loop di acquisizione/validazione slug (solo qui), gestione errori con `EXIT_CODES`.
- **Refactor `onboarding_full_main`**: estratte funzioni dedicate per ridurre complessità e migliorare i test.
  - `_run_preview(...)` (controllo Docker + avvio preview HonKit in detached, stop automatico in `finally`).
  - `_maybe_push(...)` (conferma in interattivo, verifica `GITHUB_TOKEN`, push e cleanup opzionale).
  - Comportamento invariato lato CLI/flag; logging strutturato coerente.

### Added
- **Retry con tetto massimo (Drive)**: in `drive_utils._retry(...)` introdotto `max_total_delay` (default **60s**).
  - Se il budget di sleep cumulato verrebbe superato: warning e `TimeoutError` immediato.
  - Metriche aggiornate (`backoff_total_ms`) e logging chiaro del superamento soglia.

### Migration Notes
- Se script esterni si affidavano a prompt nei moduli per lo *slug*, ora devono:
  - passare lo slug esplicitamente **oppure**
  - gestire `ConfigError` a livello di orchestratore (mappando a `EXIT_CODES`).
- Facoltativo: mappare `TimeoutError` del retry Drive a un exit code dedicato (o a `DriveDownloadError`) negli orchestratori.

### Docs
- Aggiornare brevemente **developer_guide** / **architecture** per riflettere:
  - validazione slug lato orchestratori,
  - estrazione helper `_run_preview` e `_maybe_push`.

## [1.0.4] - 2025-08-18
### Added
- Introduzione del campo `run_id` in `ClientContext`, propagato automaticamente ai logger e alle eccezioni.
- Supporto `run_id` in `PipelineError` e nei filtri di logging per correlare i log di una singola esecuzione.

### Changed
- `pre_onboarding.py` e `onboarding_full.py`: logging unificato con `run_id`, gestione migliorata degli errori e mapping coerente su `EXIT_CODES`.
- `onboarding_full.py`: nuova policy di validazione `require_env` che consente modalità offline (`--no-drive`, `--dry-run`, `--allow-offline-env`).
- `onboarding_full.py`: introdotto limite configurabile di retry per il preview Docker (`--docker-retries`), evitando loop infiniti.
- `tools/cleanup_repo.py`: sostituito `raise SystemExit(...)` con `sys.exit(...)` per coerenza e leggibilità; logging degli errori arricchito con `logger.exception`.

### Fixed
- Rimossi i `raise Exception` generici residui: ora tutte le eccezioni sono tipizzate (`PipelineError`, `ConfigError`, ecc.).
- Logging coerente su tutti gli orchestratori e tool, evitando duplicazioni o perdita di messaggi.

### Added
- Supporto alla redazione centralizzata dei log tramite `is_log_redaction_enabled`, esteso a tutte le funzioni sensibili (Drive, GitHub, preview).
- Cleanup automatico del container Docker di anteprima al termine della procedura (`onboarding_full`).
- Costanti strutturali centralizzate in `constants.py` per directory, file e MIME types, ora utilizzate anche negli orchestratori.
- Gestione di `DRIVE_PARENT_FOLDER_ID` come env opzionale, con precedenza su `DRIVE_ID` se presente.

### Changed
- Allineamento completo degli orchestratori (`pre_onboarding.py`, `onboarding_full.py`) alle costanti `OUTPUT_DIR_NAME`, `LOGS_DIR_NAME`, `LOG_FILE_NAME`.
- Migliorata l’ordine dei blocchi `except`: catch specifici ora precedono quelli generici, evitando mascheramenti.
- Logging arricchito con metadati contestuali e uniformato su unico file log (`onboarding.log`).
- `ConfigError`, `PreviewError` e altre eccezioni tipizzate gestite in maniera consistente negli orchestratori.
- Conversione `content_utils` resa più robusta: gestione gerarchie annidate, `SUMMARY.md` e `README.md` idempotenti.
- `drive_utils` migliorato con retry con jitter, download ricorsivo dei PDF e compatibilità con Shared Drives.
- `github_utils` aggiornato con push sicuro, gestione branch di default e credenziali via `GIT_HTTP_EXTRAHEADER`.
- `exceptions.py`: metodi `__str__` sicuri, senza esposizione di token o ID completi (mascheramento automatico).
- `path_utils`: validazione slug tramite regex configurabile, caching e funzioni di sanitizzazione filename.
- `cleanup_utils`: rimozione sicura di artefatti `.git` legacy dopo il push.

### Fixed
- Risolti casi in cui stringhe vuote nelle env venivano considerate valide (ora trattate come mancanti).
- Bug nel logging di errori in `path_utils` (ora più chiaro e consistente).
- Gestione corretta dei fallback quando `DRIVE_ID` o `drive_raw_folder_id` non sono definiti.

## [1.0.4] - 2025-08-18

### Added
- **Redazione log (opt-in)**: introdotto e propagato il flag `redact_logs` per evitare leakage di segreti nei messaggi di log.
  - `pipeline.drive_utils`: supporto a `redact_logs` in `_retry`, `create_drive_folder`, `upload_config_to_drive_folder`,
    `create_drive_structure_from_yaml` (e `_create_remote_tree_from_mapping`), `download_drive_pdfs_to_local`.
  - `pipeline.github_utils`: nuovo parametro `redact_logs` per mascherare token/URL nei log e nei messaggi di errore.
  - `pipeline.gitbook_preview`: nuovo parametro `redact_logs` per redigere messaggi di build/serve (le eccezioni restano integre).
- **Toggle centralizzato redazione**: `pipeline.env_utils.is_log_redaction_enabled(context)` per determinare a runtime se attivare la redazione.
- **Utility ambiente tipizzate**: `require_env`, `get_bool`, `get_int` e `redact_secrets` (retro-compat con `get_env_var`).

### Changed
- **Orchestratori**:
  - `pre_onboarding.py`: utilizza il toggle centralizzato e passa `redact_logs` a `create_drive_folder` e `upload_config_to_drive_folder`.
  - `onboarding_full.py`: utilizza il toggle centralizzato e passa `redact_logs` a `download_drive_pdfs_to_local`,
    `run_gitbook_docker_preview` e `push_output_to_github`.
- **Logger unificato**: `pipeline.logging_utils` allineato (formatter unico, filtro `slug`, rotazione opzionale, fallback console-only).

### Fixed
- `onboarding_full.py`: corretto l’argomento CLI `--skip-push` → `action="store_true"`.

### Security
- Redazione proattiva di token/segret* nei log tramite `redact_secrets` e flag `redact_logs` propagato dagli orchestratori.

---

#### Prossimo passo
Estendere il supporto `redact_logs` e la coerenza del logging a **tutti** i moduli restanti (`content_utils.py`, `config_utils.py`, `cleanup_utils.py`, …), aggiornare la documentazione sull’uso del toggle e aggiungere smoke test per verificare la redazione e le metriche di retry.

## [2025-08-18] Onboarding pipeline – sessione refactor e bugfix

### 🚀 Nuove funzionalità
- Aggiunto prompt per **pulizia artefatti post-push** in `onboarding_full`.
- Introdotto controllo interattivo Docker con possibilità di **skip** o **retry** (preview opzionale).

### 🛠 Correzioni
- Ripristinato funzionamento `push_output_to_github` con gestione coerente del flag `--push`.
- Corretto bug nei log di `content_utils` con **rebind del logger** al file cliente.
- `cleanup_utils` reso puro modulo di utility (niente `input()`), con logica interattiva spostata su `onboarding_full`.
- `onboarding_full`: preview container Docker ora stoppato sempre in `finally`.

### 📖 Note architetturali
- Confermata eliminazione degli **alias legacy** (`--skip-drive`, `--skip-push`) a partire da v2.0.
- Pulizia e semplificazione del flusso: input utente consentito solo negli orchestratori, utility ridotte a funzioni pure.

## [PR-1] - 2025-08-17
### Changed
- Refactor orchestratori e pipeline per maggiore robustezza e maneggevolezza.
- Unificazione gestione logger: introdotto file unico `onboarding.log` per cliente, con propagazione coerente dei messaggi.
- Migliorata idempotenza nei moduli di orchestrazione (`pre_onboarding.py`, `onboarding_full.py`, ecc.) senza alterare il flusso della pipeline.
- Gestione Docker resa opzionale: se non disponibile, la preview viene saltata (non-interactive) o confermata da prompt (interactive).
- Preview HonKit resa non bloccante: avvio *detached* e stop automatico all’uscita.
- Pulizia selettiva dei container Docker di preview per evitare residui tra run successivi.

## [0.6.0] - 2025-08-17
### Added
- Creati i test unitari per `github_utils.py` con copertura dei casi principali:
  - token mancante
  - assenza di file `.md`
  - `confirm_push=False`
  - flusso "happy path" con copia selettiva dei file e branch personalizzato
- Creati i test unitari per `drive_utils.py` con gestione dei casi edge (es. slug mancante).

### Fixed
- Corretto bug di indentazione in `tests/test_github_utils.py` che impediva la raccolta dei test.
- Migliorata la robustezza nella cattura dei log (`caplog`) per i test di `github_utils`.

### Changed
- Aggiornata la logica dei test per assicurare che vengano intercettati i log corretti e che i comandi GitHub/Git non vengano invocati quando non necessario.

## [1.0.5] — 2025-08-17
### Added
- `tools/refactor_tool.py`: nuova modalità **“Trova (solo ricerca)”** che elenca i file e il numero di occorrenze senza modificare nulla.

### Changed
- `tools/cleanup_repo.py`: ora **sempre interattivo** con prompt per slug, opzioni “includi artefatti globali” e “elimina repo remoto (gh)”, **conferma finale**, path-safety, **logging strutturato** (gli “skip path assente” passano a **DEBUG**), niente `sys.exit()` nel modulo, bootstrap `PYTHONPATH`.
- `tools/gen_dummy_kb.py`: riallineato al comportamento del repo → **slug fisso `dummy`**, generazione di `book/`, `config/`, `raw/` guidata da `config/cartelle_raw.yaml` e `config/pdf_dummy.yaml`, prompt **solo** per creare la cartella `repo/` di test; **fallback `.txt`** se `fpdf` manca; logging strutturato e path-safety.
- `tools/refactor_tool.py`: menu aggiornato con **1) Trova**, **2) Trova & Sostituisci**, **3) Esci**; anteprima conteggi, conferma prima dell’applicazione, **backup `.bak`**, filtri predefiniti per estensioni/cartelle escluse, logging a DEBUG per skip/letture fallite.

### Removed
- `tools/validate_structure.py`: rimosso (script non referenziato/obsoleto).

### Compatibility
- Nessun breaking change: aggiornamenti UX e robustezza dei tools, pipeline invariata.


## [1.0.4] — 2025-08-17
### Added
- `path_utils`: `clear_slug_regex_cache()` per invalidare esplicitamente la cache della regex dello slug.

### Changed
- `gitbook_preview`: esecuzione **detached** di default (nessun blocco), rimozione di qualsiasi prompt dal modulo.
- `onboarding_full` (orchestratore): gestione preview **solo** lato orchestratore, con **stop automatico del container all’uscita** (anche senza push).
- `context`: **logging centralizzato** (niente `print()`), correzione slug solo in modalità interattiva.
- `github_utils`: validazione esplicita del `GITHUB_TOKEN` e chiarimento branch da `GIT_DEFAULT_BRANCH` (fallback `main`).
- Documentazione allineata: `README`, `user_guide`, `architecture`, `coding_rule`, `CONTRIBUTING`, regola base in `developer_guide`.

### Fixed
- Blocchi in CI dovuti a preview in foreground.
- Comportamento preview coerente tra modalità interattiva e non–interattiva (auto-skip senza Docker in batch).

### Compatibility
- **Nessun breaking change.** Patch di robustezza/UX; flusso invariato.

## [micro-refine docs] - 2025-08-17

### Changed
- **Docstring e commenti**: revisione estensiva per chiarezza, coerenza terminologica e uniformità di stile in tutta la pipeline.
- **Messaggi di log**: testo più informativo e coerente (senza esporre segreti), uso di emoji solo a supporto semantico.
- **Type hints e protocolli**: esplicitazione dei contratti dove utile, senza introdurre nuove dipendenze o vincoli runtime.

### Modules/Files interessati
- `src/pipeline/exceptions.py`: docstring per tutte le eccezioni; `__str__` documentato con contesto `slug/file/drive_id`.
- `src/pipeline/logging_utils.py`: docstring più complete; chiarita la logica di formatter/handler e rotazione.
- `src/pipeline/path_utils.py`: docstring e commenti su sicurezza path, regex slug da config e sanitizzazione filename.
- `src/pipeline/config_utils.py`: docstring, messaggi di errore coerenti; note su scrittura atomica/backup; validazioni pre-onboarding documentate.
- `src/pipeline/content_utils.py`: docstring su struttura annidata markdown; spiegato heading stack e invarianti di sicurezza.
- `src/pipeline/github_utils.py`: docstring, chiarito `_resolve_default_branch`; commenti su push sicuro via header PAT.
- `src/pipeline/drive_utils.py`: docstring e commenti su retry con jitter/backoff, idempotenza md5/size e BFS ricorsivo.
- `src/pipeline/gitbook_preview.py`: docstring su pre-requisiti e path-safety; chiariti passaggi `build`/`serve` in Docker.
- `src/pipeline/cleanup_utils.py`: docstring e logging per pulizia sicura dentro `base_dir`, alias retrocompat documentati.

### Notes
- Invariati: firme pubbliche, side-effects e comportamento runtime.
- Standard confermati: scrittura atomica (tmp → replace), path-safety (`is_safe_subpath`), gestione errori tipizzata.

## [1.0.3] - 2025-08-17
### Aggiunto
- Controllo Docker **prima** dell’avvio: in modalità interattiva prompt “proseguire senza anteprima?”, in non-interactive la preview viene saltata automaticamente.
- Slug **facoltativo** da CLI: supporto slug posizionale “soft” e `--slug`; se assente viene richiesto a prompt.
- Documentazione: nuove pagine `docs/policy_push.md` e `docs/versioning_policy.md`.

### Modificato
- `onboarding_full.py`: logging “early” al posto dei `print()`, messaggistica preview più sintetica, compatibilità con flag storici (`--skip-drive`, `--skip-push`) con **warning** e rimappatura a `--no-*`.
- `pre_onboarding.py`: uso coerente dell’early logger nello `__main__`, validazioni/prompt slug allineati, mappatura eccezioni → `EXIT_CODES` invariata.
- Documentazione consolidata: `README.md`, `docs/index.md`, `docs/user_guide.md`, `docs/developer_guide.md`, `docs/architecture.md`, `docs/coding_rule.md` aggiornati per riflettere preview/push, variabili d’ambiente (incl. `GIT_DEFAULT_BRANCH`) e regole operative.

### Corretto
- Pulizia import in `gitbook_preview.py` (nessun cambio di firma); piccoli refusi CLI/avvisi allineati.

### Note
- Release di **consolidamento**: nessuna modifica di flusso né delle firme pubbliche. Le nuove policy documentano il comportamento effettivo (push come riflesso dell’output locale; SemVer leggero).

## [1.0.2] - 2025-08-17
### Added
- **Download Drive ricorsivo**: `download_drive_pdfs_to_local()` ora visita l’intera gerarchia (BFS) e preserva la struttura locale, mantenendo idempotenza su `md5Checksum/size`.
- **Conversione Markdown annidata**: `convert_files_to_structured_markdown()` supporta sottocartelle; i titoli riflettono la gerarchia (output invariato: un `.md` per categoria top-level).

### Changed
- **Branch GitHub configurabile**: `push_output_to_github()` risolve il branch da `GIT_DEFAULT_BRANCH` (prima `context.env`, poi env di processo; fallback `main`). Push e checkout usano ora il branch risolto.

### Deprecated
- Nessuna voce.

### Fixed
- Aggiornati i commenti di `github_utils.py` per evitare riferimenti obsoleti a variabili non più supportate (solo docstring; nessun impatto funzionale).

### Notes
- Nessun cambio di flusso né di firma pubblica; orchestratori **immutati**.  
- Prossimo passo: **migliorie accessorie** (type hints estesi, modularità e docstring).


## [1.0.1] - 2025-08-17

### Added
- **EXIT_CODES** centralizzati in `src/pipeline/exceptions.py` e gestione delle uscite **deterministica** negli orchestratori (`pre_onboarding.py`, `onboarding_full.py`).

### Changed
- `src/onboarding_full.py`: modalità **non-interactive first**; se Docker non è disponibile, la **preview viene saltata automaticamente** in non-interattivo; alias storici gestiti con avviso; log uniformati.
- `src/pre_onboarding.py`: supporto **slug posizionale**, catch → `EXIT_CODES`, log consolidati; flusso invariato.
- `src/pipeline/logging_utils.py`: rimosso import di `ClientContext` (niente cicli), `propagate=False`, pulizia handler duplicati.
- Pulizia/robustezza senza cambiare il flusso in: `path_utils.py`, `config_utils.py` (scrittura atomica), `content_utils.py`, `drive_utils.py` (retry+jitter, idempotenza), `github_utils.py` (path-safety, push), `gitbook_preview.py` (pre-check/build/serve), `cleanup_utils.py`.

### Deprecated
- Flag **`--skip-drive`** e **`--skip-push`** (ancora accettati con **warning**). Usare **`--no-drive`** e **`--no-push`**.

### Fixed
- **Import circolare** tra `logging_utils` ↔ `context` ↔ `path_utils`.
- Messaggi e livelli di log allineati; minor hardening su path-safety e scritture atomiche.

### Notes
- **Nessuna modifica di flusso**: pipeline e UX restano quelle già documentate; questa è una release di consolidamento.


## [1.0.3] - 2025-08-17
### Aggiunto
- Controllo Docker **prima** dell’avvio: prompt immediato “proseguire senza anteprima?” in modalità interattiva; in non-interactive la preview viene saltata automaticamente.
- Slug **facoltativo** da CLI: supporto slug posizionale “soft” e `--slug`; se assente viene richiesto via prompt.

### Modificato
- `onboarding_full.py`: preview Honkit condizionata alla decisione presa nel pre-check; warning Docker **sintetico** (niente stderr rumoroso); compatibilità con flag storici (`--skip-drive`, `--skip-push`).
- `drive_utils.py`: retry esponenziale con **jitter**; `create_drive_folder` resa **idempotente** tramite lookup/reuse.
- `context.py`: logger **iniettato** nel `ClientContext` e riutilizzato da metodi di stato (niente ricreazioni ad ogni chiamata).
- `config_utils.py`: `safe_write_file` ora è atomica (tmp + replace + backup); rimosso duplicato `is_valid_slug` (fonte unica in `path_utils.py`).
- `path_utils.py`: rafforzate type hints e docstring; confermata qui la validazione slug come **punto di verità**.
- `content_utils.py`: type hints corretti per `log: Optional[logging.Logger]`.
- `env_utils.py`: allineata l’eccezione a `ConfigError` per coerenza con gli orchestratori.

### Corretto
- Import non validi e potenziali **cicli** (es. `gitbook_utils` → `gitbook_preview`, auto-import in `config_utils`); ripuliti gli import e i fallback.
- Gestione CLI: slug richiesto solo se non passato via argomenti; messaggistica più chiara nei prompt.

### Note
- Modifiche **retrocompatibili** con la 1.0.2: nessun cambio alla logica funzionale della pipeline; interventi di pulizia e robustezza.
- I test automatici saranno **rivisti nella prossima sessione** (attualmente esclusi dal refactor).


## [1.0.2] - 2025-08-16
### Modificato
- Refactoring orchestratori `pre_onboarding.py` e `onboarding_full.py` per allineamento completo con la gestione logging centralizzata.
- Aggiornata gestione percorsi dei file di configurazione (`cartelle_raw.yaml`) per coerenza con la directory `config/`.
- Migliorata robustezza caricamento configurazioni cliente in fase di avvio pipeline, con validazione più chiara e tracciabilità.
- Consolidata coerenza tra i due orchestratori nella gestione errori (`ConfigError`) e nei messaggi di log.

### Corretto
- Risolto errore di compatibilità con `get_structured_logger` rimuovendo argomenti non previsti.
- Sistemato caricamento configurazioni da `context.py` per propagare correttamente i percorsi cliente.

### Note
- Modifiche retrocompatibili con la versione **1.0.1 Stable**.
- Nessun impatto sul flusso semantico né sui moduli ausiliari (`semantic/`, `tools/`).



### **[1.0.1] – 2025-08-12**
#### **Changed**
- `onboarding_full.py`: allineato a `pre_onboarding.py` con logging arricchito, validazione config cliente con gestione errori YAML, sicurezza path e payload contestuale negli errori.
- Dipendenze (`github_utils.py`, `gitbook_preview.py`, `content_utils.py`) verificate e allineate per compatibilità con orchestratore.
- Moduli `semantic_extractor.py` e `semantic_mapping.py` revisionati per coerenza con flusso `onboarding_full`.
- Validato comportamento in modalità interattiva, test mode e batch mode.


## [1.0.1] - 2025-08-12
### Modificato
- Migliorata gestione eccezioni in `exceptions.py` con aggiunta di payload contestuale (`slug`, `file_path`, `drive_id`) e `__str__` personalizzato.
- Aggiornati `drive_utils.py`, `pre_onboarding.py` e `context.py` per propagare le informazioni di contesto nelle eccezioni.
- Validazione `slug` uniformata con supporto a regex da configurazione.
- Gestione input interattiva/non-interattiva consolidata in `pre_onboarding.py`.
- Log arricchiti con dettagli cliente e file in fase di creazione struttura locale e remota.

### Corretto
- Migliorata tracciabilità degli errori nei flussi di creazione config e strutture Drive.
- Prevenzione percorsi non sicuri con controllo `is_safe_subpath` su più funzioni critiche.


## [1.0.1] - 2025-08-12
### Miglioramenti
- **ClientContext** (`src/pipeline/context.py`): aggiunto attributo `config_dir` e inizializzazione automatica in `load()` per supporto futuro a `load_semantic_mapping`, migliorando robustezza e compatibilità.
- **GitHub Utils** (`src/pipeline/github_utils.py`): aggiunto controllo di sicurezza `is_safe_subpath` sui file `.md` prima del push per prevenire scritture non sicure fuori dalla cartella `book`.

### Note
- Modifiche retrocompatibili con la versione **1.0 Stable**.
- Nessun impatto sui flussi degli orchestratori esistenti.


## [1.0.0] - YYYY-MM-DD
### Aggiunto
- Documentazione riorganizzata in `docs/` con guide per utenti e sviluppatori
- File `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE` aggiunti per la release stabile
- Template per issue e pull request in `.github/`

### Modificato
- Migliorata formattazione `README.md` con quickstart e link rapidi
- Allineamento contenuti di `manifesto_tecnico.md` e `coding_rule.md` in documenti separati
- Struttura repository ottimizzata per pubblicazione su GitHub

### Risolto
- Correzione bug minori in estrazione keyword da PDF
- Uniformato logging a formato strutturato in tutti i moduli

---

## [0.9.2-beta] - 2025-07-28
### Modificato
- Refactoring moduli `semantic/` e `tools/` secondo regole di naming e struttura
- Aggiornamento test end-to-end e CLI
- Migliorata gestione `timmy_tags.yaml` e validazione HiTL

## [0.9.1-beta] - 2025-07-10
### Aggiunto
- Logging centralizzato completato
- Standardizzazione struttura output Markdown/YAML
- Workflow GitHub Actions aggiornato per build & test

## [0.9.0-beta] - 2025-06-15
### Aggiunto
- CLI unificata per pipeline
- Integrazione validatori semantici in orchestrazione
- Primo draft README con filosofia e obiettivi

