# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

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

