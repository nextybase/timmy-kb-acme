# 📐 Coding & Testing Rules – NeXT/Timmy Pipeline

Versione: v1.3  
Data: 2025-07-22  
Owner: NeXT Dev Team

---

## 🏷️ 1. Naming Convention

**Obiettivo:**  
Garantire coerenza, leggibilità e manutenibilità del codice su tutti i moduli della pipeline.

### 1.1 Cartelle

- **Macro-cartelle:**  
  - Codice pipeline: `src/pipeline/`
  - Moduli di enrichment/AI: `src/semantic/`
  - Configurazioni: `config/`
  - Output generato: `output/`
  - Dati/file di test: `filetest/` (con sottocartelle per tipo di file)
  - Script di test: `tests/`
- **Nomi:**  
  - Minuscolo e underscore (`_`)
  - Nome chiaro e descrittivo del dominio (`pipeline`, `semantic`, `config`, `output`, ecc.)

### 1.2 File e Moduli Python

- **Regole:**  
  - Solo minuscolo, underscore per separare concetti (`content_utils.py`, `config_utils.py`)
  - Un file = un dominio/ruolo funzionale.
  - Vietato: nomi generici (`helpers.py`, `main.py`, ecc.).
- **Esempi:**  
  - `drive_utils.py`, `github_utils.py`, `logging_utils.py`, `content_utils.py`, `cleanup.py`, `gitbook_preview.py`
  - Orchestratori: `pre_onboarding.py`, `onboarding_full.py`
  - Moduli semantic: `semantic_extractor.py`, `semantic_mapping.py`

### 1.3 Funzioni e Variabili

- `snake_case` per funzioni e variabili.
- Nome = verbo + oggetto (`download_pdfs_from_drive`, `generate_summary_md`)
- Evitare abbreviazioni oscure, vietate le “one letter”.
- **Costanti:** tutto maiuscolo, con underscore (`OUTPUT_DIR_TEMPLATE`).

### 1.4 Classi

- `PascalCase` (es. `ClientManager`, `PdfConverter`).

### 1.5 Slug, Output e Repo

- Slug cliente: solo `[a-z0-9-]`, separatore: `-`, no spazi/underscore (`timmy-kb-mydemo`)
- Cartelle output: `output/timmy-kb-<slug>/`
- File Markdown: minuscolo, trattino basso dove serve.
- Repo GitHub: `timmy-kb-<slug>`, no maiuscole/underscore.

### 1.6 Nuovi moduli/funzioni

- Verifica se dominio esiste prima di aggiungere un nuovo modulo in `pipeline/`.
- Suffix `_utils.py` per moduli di servizio.
- Ogni funzione pubblica deve avere docstring chiara.

---

## 📝 2. Logging Rules

**Obiettivo:**  
Tracciabilità e debugging robusto, audit sicuro, nessun `print()` in produzione.

### 2.1 Centralizzazione

- Un solo modulo: `logging_utils.py` in `src/pipeline/`.
- Ogni modulo carica così:
  ```python
  from pipeline.logging_utils import get_logger
  logger = get_logger("nome_modulo")
  ```

### 2.2 Formato e livelli

- Formato:  
  `YYYY-MM-DD HH:MM:SS | LEVEL | modulo | messaggio`
- Emoji per leggibilità: ✅, ⚠️, ❌, ℹ️, 📥, ecc.
- Livelli: DEBUG (sviluppo), INFO (step normali), WARNING (anomalie), ERROR (errori), CRITICAL (crash).
- Log su console di default, su file se specificato da .env o config.

### 2.3 Policy

- Nessuna funzione usa print() tranne test/script CLI.
- Log ogni step chiave.
- Eccezioni sempre loggate con .error() o .exception().
- Nessun log duplicato o ambiguo.
- Livello log default: INFO in produzione, DEBUG solo se richiesto per troubleshooting.

### 2.4 Esempio

```python
logger.info("✅ PDF convertito: %s", file.name)
logger.error("❌ Errore conversione PDF: %s", e, exc_info=True)
```

---

## 🧪 3. Testing Rules

**Obiettivo:**  
Garantire robustezza, ripetibilità, pulizia e scalabilità dei test.

### 3.1 Struttura e convenzioni

- Tutti gli script di test sono in `/tests/`.
- File di input per i test sono in `/filetest/` con sottocartelle per tipologia (pdf/, docx/, yaml/, ecc.).
- Esempio: `/filetest/pdf/` per test PDF → markdown.
- Gli output dei test vanno sempre in `/output/timmy-kb-dummytest/`.
- Cleanup sempre a fine test (opzione per cancellare i file generati).

### 3.2 Regole naming test

- I test non hanno mai “test” nel nome file (es: `pdf2md_preview.py` e non `test_pdf2md.py`).
- Il nome è descrittivo dello step/funzione che testano.
- L’utente “dummytest” è riservato per ogni test (output e slug).

### 3.3 Regole di comportamento

- Nessun dato reale mai processato fuori da ambiente di test.
- I test sono sempre idempotenti: nessun residuo lasciato tra run successivi.
- I test validano tutta la pipeline:
  - Setup cartelle di test
  - Parsing/conversione/tagging
  - Generazione README.md/SUMMARY.md
  - Preview con Docker (opzionale)
  - Cleanup
- Print consentiti solo per step chiave di setup/cleanup, non per log di dettaglio.

### 3.4 Best practice

- Aggiungere nuovi script di test per ogni nuova funzione/core feature.
- Validare sempre su file “dummy” diversi (anche edge case).
- Formalizzare nuove convenzioni qui ogni volta che si evolve il sistema.

---

## 📦 4. Documentazione & Policy di aggiornamento

- Ogni nuovo modulo/funzione/documentazione deve rispettare queste regole.
- Aggiornare questo file ogni volta che si aggiunge/cambia una policy strutturale.
- Ogni PR che modifica regole di coding, logging, testing deve indicare la sezione modificata di questo file.
- Il README.md deve sempre linkare a questa pagina per policy di coding.

---

## 📚 Allegati

- Esempi completi in `logging_utils.py`, `onboarding_full.py`, `pdf2md_preview.py`.
- Policy naming, logging, testing sempre versione-control in questo file.
- Per ogni dubbio, evoluzione o PR sulle policy,  
  aprire sempre issue/PR GitHub con motivazione e sezione di questa policy toccata.
