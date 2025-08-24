# Coding Rules — Timmy-KB (v1.2.0)

Regole operative per scrivere e manutenere il codice della pipeline Timmy-KB. L’obiettivo è garantire stabilità, tracciabilità, sicurezza e comportamento deterministico (specie in modalità batch) attraverso uno stile di codice coerente. Ogni nuova implementazione deve fare riferimento alla **Developer Guide** e alla descrizione dell’**Architettura**, mantenendo compatibilità locale e privilegiando il riuso di funzioni già presenti, proponendo aggiornamenti solo se strettamente necessario.

---

## 1) Linguaggio, stile, tipizzazione

- **Python ≥ 3.10** – usare le feature del linguaggio (type hints, match-case) mantenendo compatibilità.
- **Type hints** – annotazioni obbligatorie per tutte le funzioni pubbliche e strutture dati complesse.
- **Docstring** – brevi e chiare, stile Google. Solo esempi se chiariscono casi non ovvi.
- **Naming** – snake\_case per variabili/funzioni, PascalCase per classi, MACRO\_CASE per costanti. Nomi esplicativi.
- **Import** – ordine: standard, terze parti, locali. Preferire import assoluti.
- **Formattazione** – PEP 8, Black, Ruff. I commit devono superare pre-commit hooks.
- **Commenti** – spiegare *perché*, non il *cosa*. Evitare superflui.

---

## 2) Orchestratori vs Moduli

- **Orchestratori** – UX e flussi: parsing CLI, prompt (solo interattivo), gestione flag (--non-interactive, --dry-run, --no-drive, --push, etc.), anteprima Docker, gestione eccezioni → exit code. Solo qui `sys.exit()`.
- **Moduli** – operazioni tecniche: Drive, conversione file, push GitHub. Nessun input utente né `sys.exit()`. Sollevano eccezioni.
- **Output utente** – solo orchestratori, via logger. Moduli restituiscono valori o eccezioni.
- **Batch-safe** – i moduli devono girare senza interazione. Orchestratori gestiscono batch vs interattivo.

---

## 3) Logging ed errori

- **No print()** – tutto via logger strutturato (`get_structured_logger`). Livelli: DEBUG, INFO, WARNING, ERROR.
- **Metadati nei log** – usare `extra={}` con slug, path, ecc.
- **Niente segreti nei log** – usare redazione centralizzata (`compute_redact_flag`, `_mask`).
- **Eccezioni tipizzate** – usare classi specifiche (`ConfigError`, `PreviewError`, ecc.). Orchestratori mappano su EXIT\_CODES.
- **Gestione deterministica** – niente catch-all generici nei moduli. Lasciar propagare se imprevisti.
- **Messaggi chiari** – spiegare il problema, non messaggi generici.

---

## 4) I/O, sicurezza e atomicità

- **Pathlib & encoding** – sempre `Path`, `encoding="utf-8"`, context manager.
- **Path traversal** – usare `is_safe_subpath`.
- **Scritture atomiche** – usare `safe_write_text`/`safe_write_bytes` con `atomic=True`. Backup `.bak` per config critici.
- **No segreti su disco** – non salvare token, credenziali. Solo PDF originali ammessi.
- **Chiusura risorse** – sempre context manager.

---

## 5) Configurazioni e cache

- **YAML config** – sempre `yaml.safe_load`. Default sensati o `ConfigError`.
- **Regex slug** – definita in config/config.yaml, cache in path\_utils. Invalidate con `clear_slug_regex_cache()`.
- **Env centralizzate** – usare `env_utils.get_env_var`. Vietato os.environ sparsi.
- **Cache runtime** – isolate al modulo, invalidabili con funzioni dedicate.

---

## 6) Subprocess, Docker, GitHub

- **Comandi esterni** – sempre `proc_utils.run_cmd(...)` con timeout, retry/backoff, cattura `stdout/stderr`. Vietato `shell=True` se non indispensabile.
- **Docker** – preview via `adapters.preview` (API uniforme). Stop via orchestratore.
- **Git/GitHub** – gestiti in `github_utils.py`. Validare precondizioni (es. `GITHUB_TOKEN`). Push incrementale, forzato solo con `--force-push` + `--force-ack`. Sempre `--force-with-lease`.
- **Token** – mai nell’URL, solo header. Mascherare nei log.

---

## 7) Drive e rete

- **Retry con backoff** – implementare exponential backoff + jitter (vedi `drive/client.py`). Loggare tentativi.
- **Idempotenza download** – saltare file invariati (MD5 + size).
- **Gerarchia** – RAW locale deve rispecchiare Drive. BOOK rispecchia RAW.
- **Metriche** – loggare numero file scaricati, retry, skip.
- **Redazione dati** – loggare ID parziali (inizio/fine) se `redact_logs=True`.

---

## 8) Compatibilità e versioning

- **SemVer** – PATCH = bugfix/refactor compatibile. MINOR = nuove feature. MAJOR = cambi di API.
- **No breaking in PATCH** – vietato cambiare default o rimuovere opzioni.
- **Test di compatibilità** – provare comandi base dopo ogni modifica.

---

## 9) Test minimi (manuali)

Prima di una PR, eseguire:

1. **Pre-onboarding (locale)**
   ```bash
   py src/pre_onboarding.py --slug demo --non-interactive --dry-run
   ```
2. **Onboarding base (no Drive, no push)**
   ```bash
   py src/onboarding_full.py --slug demo --no-drive --non-interactive
   ```
3. **Onboarding con Docker** (interattivo, conferma preview, push No, cleanup Yes).
4. **Push batch** (con `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH=main`). Verificare commit + push senza force.

---

## 10) Qualità del codice

- **Funzioni piccole** – ogni funzione fa una cosa precisa.
- **Chiarezza > performance** – ottimizzare solo con evidenza, commentare trick.
- **No duplicazione** – DRY, estrarre in util quando sensato.
- **Testabilità** – funzioni pure, dipendenze iniettate (logger, context).
- **TODO chiari** – annotare solo con breve spiegazione. Rimuovere codice morto.
- **Consistenza** – nomi, log e emoji coerenti (✅ successo, ⚠️ warning, ⏭️ skip).
- **API coerenti** – tutte le funzioni esposte dagli adapter hanno firma `(context, logger, **opts)` o variante coerente (PR-4).

---

### Esempi rapidi

**Logger corretto in un modulo**

```python
from pipeline.logging_utils import get_structured_logger
logger = get_structured_logger("pipeline.content_utils")

def convert_pdf_to_md(context, pdf_path):
    logger.info("Convertendo PDF in Markdown", extra={"slug": context.slug, "file_path": str(pdf_path)})
    try:
        ...  # conversione
        logger.info("Conversione completata", extra={"slug": context.slug, "file_path": str(pdf_path)})
    except Exception as e:
        logger.error(f"Errore durante la conversione: {e}", extra={"slug": context.slug, "file_path": str(pdf_path)})
        raise
```

**Errore tipizzato + mapping orchestratore**

```python
from pipeline.exceptions import PreviewError

def generate_preview(context):
    if error_docker:
        raise PreviewError("Build anteprima fallita", slug=context.slug)

# Nell’orchestratore
from pipeline.exceptions import EXIT_CODES, PreviewError
try:
    generate_preview(context)
except PreviewError as e:
    logger.error(str(e))
    sys.exit(EXIT_CODES["PreviewError"])
```

*(Gli esempi mostrano come loggare correttamente con contesto e propagare errori tipizzati all’orchestratore.)*

---

