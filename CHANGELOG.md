# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

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

