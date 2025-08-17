# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

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

