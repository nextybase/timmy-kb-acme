# 📏 Naming & Logging Rules – NeXT Pipeline

Versione: v1.2.3  
Data: 2025-07-21  
Owner: NeXT Dev Team

---

## 🏷️ 1. Naming Convention

**Obiettivo:**  
Garantire coerenza, leggibilità e manutenibilità del codice in ogni componente della pipeline.  
Ogni nuovo file, funzione, variabile o cartella deve rispettare queste regole **senza eccezioni**.

---

### 1.1 Cartelle

- **Macro-cartelle:**  
  - Tutto il codice della pipeline sta in `src/pipeline/`
  - Moduli di enrichment/AI stanno in `src/semantic/`
  - Configurazioni in `config/`
  - Output generato in `output/`
- **Nomi:**  
  - Solo caratteri minuscoli e underscore (`_`) dove serve.  
  - Nomi autoesplicativi del dominio funzionale:  
    - `pipeline`, `semantic`, `config`, `output`, `docs`, ecc.

---

### 1.2 File e Moduli Python

- **Regole generali:**  
  - Tutti i nomi file Python **minuscoli**, con underscore per separare concetti (`content_utils.py`, `drive_utils.py`, `config_utils.py`)
  - Un file = un dominio/ruolo funzionale.
  - Niente nomi generici come `helpers.py`, `misc.py` o `main.py`.

- **Esempi corretti:**  
  - `drive_utils.py`, `github_utils.py`, `logging_utils.py`, `content_utils.py`, `config_utils.py`, `cleanup.py`, `gitbook_preview.py`
  - **Script di orchestrazione**:  
    - `pre_onboarding.py`, `onboarding_full.py` (devono essere self-descriptive)
  - **Moduli semantic**:  
    - `semantic_extractor.py`, `semantic_mapping.py`

---

### 1.3 Funzioni e Variabili

- **Funzioni e variabili:**  
  - Sempre in `snake_case` (tutto minuscolo, separazione con `_`).
  - Nome = *verbo + oggetto* se rappresentano azioni/processi (`download_pdfs_from_drive`, `generate_summary_md`, `run_gitbook_preview`).
  - Evitare abbreviazioni oscure o “one letter” (`dl_pdf`, `fn1` sono vietati).
- **Costanti:**  
  - Solo `UPPER_SNAKE_CASE` (`DRIVE_ID`, `OUTPUT_DIR_TEMPLATE`).

---

### 1.4 Classi

- **Classi:**  
  - Sempre in `PascalCase` (es. `ClientManager`, `PdfConverter`).
  - Devono rappresentare oggetti o concetti non funzioni.

---

### 1.5 Slug, Output e Repo

- **Slug cliente:**  
  - Solo caratteri minuscoli `[a-z0-9-]`, separatore: trattino `-`, NO spazi, NO underscore.
  - Esempio: `timmy-kb-mydemo`
- **Cartelle output:**  
  - `output/timmy-kb-<slug>/`
- **File Markdown:**  
  - Tutti i nomi file markdown **minuscoli**, trattino basso dove serve (`glossario.md`, `policy_privacy.md`)
- **Repo GitHub:**  
  - Formato: `timmy-kb-<slug>`  
  - NO maiuscole o underscore.

---

### 1.6 Policy nuovi moduli/funzioni

- **Nuovo modulo:**  
  - Prima verifica che il dominio non esista già in pipeline/.
  - Nome sempre `<dominio>_utils.py` se sono funzioni di servizio su uno specifico tema.
- **Nuova funzione:**  
  - Nome sempre descrittivo, con docstring.
- **Nuova classe:**  
  - Solo se realmente serve OOP; no classi “contenitore”.

---

### 1.7 Documentazione

- Ogni modulo deve avere docstring iniziale con scopo e autore.
- Ogni funzione pubblica deve avere docstring con input/output e comportamento.
- Aggiornare sempre il presente file e README se introduci naming policy nuova.

---

## 📝 2. Logging Rule

**Obiettivo:**  
Garantire tracciabilità completa, debugging facilitato e audit sicuro su tutte le fasi della pipeline,  
ev itando stampe libere (`print()` vietato) e favorendo logging strutturato centralizzato.

---

### 2.1 Centralizzazione

- Un solo modulo logging: `logging_utils.py` in `src/pipeline/`
- Ogni modulo carica il logger tramite:
  ```python
  from pipeline.logging_utils import get_logger
  logger = get_logger("nome_modulo")  # Esempio: get_logger("drive_utils")
```

### 2.2 Formato e livelli

Formato log obbligatorio:

    2025-07-21 17:51:33 | INFO | pipeline.drive_utils | 📥 Scaricato PDF: identity.pdf

Struttura: YYYY-MM-DD HH:MM:SS | LEVEL | modulo | messaggio

Emoji consentite per migliorare la leggibilità: ✅, ⚠️, ❌, ℹ️, 📥, ecc.

Livelli obbligatori:

- DEBUG (dettagli, solo se attivato)
- INFO (esito step normale)
- WARNING (anomalie gestibili)
- ERROR (errori bloccanti/exception gestita)
- CRITICAL (crash/fallimento pipeline)

### 2.3 Configurazione

- Livello di log di default: INFO
- Log su console sempre attivo; log su file se specificato (LOG_FILE in .env o config)
- Livello e path file configurabili da .env (es: LOG_LEVEL=DEBUG, LOG_FILE=logs/onboarding.log)
- Supporto a rotazione file (opzionale, futuro).

### 2.4 Policy d’uso

- Nessuna funzione deve usare print().
- Ogni step significativo deve loggare l’esito (successo/errore).
- Tutte le eccezioni devono essere loggate con logger.error o logger.exception (incluso stacktrace).
- I messaggi di log devono essere sempre contestuali e localizzati (chi, cosa, esito).
- Non duplicare log o inserire messaggi ambigui.

### 2.5 Esempio

```python
from pipeline.logging_utils import get_logger
logger = get_logger("github_utils")

def do_push(config):
    try:
        ...
        logger.info("🚀 Deploy su GitHub completato per repo: %s", config["github_repo"])
    except Exception as e:
        logger.error("❌ Errore deploy GitHub: %s", e, exc_info=True)
```

### 2.6 Best practice future

- Logging JSON per AI/analysis (python-json-logger, Loguru)
- Colori in console via RichHandler
- logging.yaml centralizzato per config avanzate

---

📚 Allegati
Esempi completi nei moduli logging_utils.py e orchestratori (onboarding_full.py, ecc.)

Aggiornare sempre questa convenzione ad ogni evoluzione strutturale.

Per ogni dubbio, PR o modifica a queste policy, aprire issue o PR su GitHub con motivazione.

