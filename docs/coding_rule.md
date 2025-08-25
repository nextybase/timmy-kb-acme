## Coding Rules — Timmy-KB (v1.2.2)

Regole operative per scrivere e manutenere il codice della pipeline Timmy-KB. L’obiettivo è garantire stabilità, tracciabilità, sicurezza e comportamento deterministico (specie in modalità batch) attraverso uno stile di codice coerente. Ogni nuova implementazione deve fare riferimento alla **Developer Guide** e alla descrizione dell’**Architettura**, mantenendo compatibilità locale e privilegiando il riuso di funzioni già presenti, proponendo aggiornamenti solo se strettamente necessario.

---

## 1) Linguaggio, stile, tipizzazione

- **Python ≥ 3.10** – usare le feature moderne (type hints, pattern matching) mantenendo compatibilità.
- **Type hints** – obbligatorie per tutte le funzioni pubbliche e strutture dati complesse.
- **Docstring** – brevi e chiare, stile Google; esempi solo se chiariscono casi non ovvi.
- **Naming** – snake_case per variabili/funzioni, PascalCase per classi, MACRO_CASE per costanti. Nomi esplicativi.
- **Import** – ordine: standard, terze parti, locali. Preferire import assoluti.
- **Formattazione** – PEP 8, Black, Ruff. I commit devono superare i pre-commit hooks.
- **Commenti** – spiegare *perché*, non *cosa*. Evitare superflui.

---

## 2) Orchestratori vs Moduli

- **Orchestratori** – UX e flussi: parsing CLI, prompt (solo interattivo), gestione flag (`--non-interactive`, `--dry-run`…), preview Docker, gestione eccezioni → exit code. Solo qui `sys.exit()`.
- **Moduli** – operazioni tecniche (Drive, conversione, push). Nessun input utente né `sys.exit()`. Sollevano eccezioni tipizzate.
- **Output utente** – solo orchestratori, via logger. I moduli restituiscono valori o eccezioni.
- **Batch-safe** – i moduli devono funzionare senza interazione; orchestratori gestiscono batch vs interattivo.
- **Test e strumenti dummy** – `gen_dummy_kb.py` produce sandbox completa con PDF sintetici e CSV iniziali; usato come base per i test automatizzati in `tests/`.

---

## 3) Logging ed errori

- **No `print()`** – tutto via logger strutturato (`get_structured_logger`). Livelli: DEBUG, INFO, WARNING, ERROR.
- **Metadati nei log** – usare `extra={}` con slug, path, ecc.
- **Niente segreti nei log** – usare redazione centralizzata (`compute_redact_flag`). Mai loggare token in chiaro.
- **Eccezioni tipizzate** – usare classi specifiche (`ConfigError`, `PreviewError`, `PushError`, …). Gli orchestratori mappano su `EXIT_CODES`.
- **Determinismo** – niente catch-all generici nei moduli. Lasciar propagare se imprevisti.
- **Messaggi chiari** – spiegare il problema e il contesto.

---

## 4) I/O, sicurezza e atomicità

- **Pathlib & encoding** – sempre `Path`, `encoding="utf-8"`.
- **Path traversal (SSoT)** – `pipeline.path_utils.ensure_within` come guardia forte. `is_safe_subpath` solo per check soft.
- **Scritture atomiche** – usare `safe_write_text/bytes` con `atomic=True`. Per file critici, backup `.bak`.
- **No segreti su disco** – non salvare token/credenziali.
- **Chiusura risorse** – sempre context manager; nessun fd appeso.
- **Compatibilità Windows** – evitare caratteri Unicode non supportati nei log stdout; usare emoji/testo solo se compatibili con `cp1252`.

---

## 5) Configurazioni e cache

- **YAML config** – sempre `yaml.safe_load`. Default sensati o `ConfigError`.
- **Regex slug** – definita in `config/config.yaml`, cache in `path_utils`. Invalidate con `clear_slug_regex_cache()`.
- **Env centralizzate** – usare `env_utils.get_env_var`.
- **Cache runtime** – isolate al modulo, invalidabili.

---

## 6) Subprocess, Docker, GitHub

- **Comandi esterni** – wrapper (`proc_utils.run_cmd(...)`) con timeout, retry/backoff. Evitare `shell=True`.
- **Docker** – preview via `adapters.preview`. Lo stop è orchestrato dagli orchestratori.
- **Split orchestratori** – `semantic_onboarding.py` → conversione/enrichment/preview. `onboarding_full.py` → push.
- **GitHub** – push via `pipeline.github_utils`. Precondizioni valide (`GITHUB_TOKEN`). Force solo con consenso (`--force-push` + `--force-ack`) e `--force-with-lease`.
- **Token** – mai in URL; solo header. Mascherare sempre nei log.

---

## 7) Drive e rete

- **Uso limitato a pre-onboarding** – Drive solo per creare struttura remota e caricare `config.yaml`.
- **Retry con backoff** – exponential + jitter (vedi `drive/client.py`).
- **Idempotenza download** – saltare file invariati (MD5 + size).
- **Gerarchia** – RAW locale rispecchia Drive; BOOK rispecchia RAW.
- **Metriche** – loggare numero file scaricati, retry, skip.
- **Redazione dati** – loggare ID parziali se `redact_logs=True`.

---

## 8) Compatibilità e versioning

- **SemVer** – PATCH = bugfix compatibili. MINOR = nuove feature. MAJOR = cambi API.
- **No breaking in PATCH** – vietato cambiare default o rimuovere opzioni.
- **Smoke test** – eseguire i comandi base dopo ogni modifica. Aggiungere test quando serve.
- **Tests Pytest** – test principali sotto `tests/`, es. `test_dummy_pipeline.py` che valida coerenza PDF/CSV e generazione sandbox.

---

## 9) Test minimi

Prima di una PR, eseguire:

```bash
# Pre-onboarding (locale)
py src/pre_onboarding.py --slug demo --non-interactive --dry-run

# Tag onboarding (CSV + stub)
py src/tag_onboarding.py --slug demo --source local --local-path ./some-pdfs --non-interactive --proceed

# Semantic onboarding (conversione + preview)
py src/semantic_onboarding.py --slug demo --non-interactive --no-preview

# Push (solo GitHub)
set GITHUB_TOKEN=...  # o esportare in .env
py src/onboarding_full.py --slug demo --non-interactive
```

---

## 10) Qualità del codice

- **Funzioni piccole** – ogni funzione fa una cosa precisa.
- **Chiarezza > performance** – ottimizzare solo se necessario, commentare i trick.
- **No duplicazione** – DRY, estrarre in util quando sensato.
- **Testabilità** – funzioni pure, dipendenze iniettate (logger, context).
- **TODO chiari** – annotare con breve spiegazione; rimuovere codice morto.
- **Consistenza** – nomi, log e emoji coerenti (✅ successo, ⚠️ warning, ⏭️ skip).
- **API coerenti** – gli adapter espongono `(context, logger, **opts)` o variante coerente.

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

