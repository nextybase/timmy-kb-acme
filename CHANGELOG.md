# 📓 Changelog – Timmy-KB

Tutte le modifiche rilevanti al progetto saranno documentate in questo file.

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
