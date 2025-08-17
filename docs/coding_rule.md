# Coding Rules — Timmy‑KB (v1.0.3 Stable)

Regole **operative** per scrivere e manutenere il codice della pipeline. Obiettivo: stabilità, tracciabilità e comportamento deterministico in batch.

---

## 1) Linguaggio, stile, tipizzazione
- **Python ≥ 3.10** (pattern matching opzionale, `typing` completo).
- **Type hints obbligatori** su funzioni pubbliche; `dataclasses` quando utile.
- **Docstring brevi** (stile Google) con esempi solo quando servono.
- **Naming**: `snake_case` per funzioni/variabili, `UPPER_CASE` per costanti, classi in `PascalCase`.
- **Import order**: stdlib → terze parti → locali; **import assoluti** dove possibile.
- Strumenti consigliati: **Ruff**, **Black**, **Mypy**, **pre‑commit**.

---

## 2) Orchestratori vs Moduli
- **Orchestratori**: gestiscono UX/CLI (prompt, conferme), mapping **eccezioni → `EXIT_CODES`**, selezione modalità (`--non-interactive`), stop automatico della preview.
- **Moduli**: eseguono **azioni tecniche** e sono **batch‑safe**: **vietati** `input()` e `sys.exit()`; niente prompt.
- Output umano (messaggi) **solo** negli orchestratori; i moduli espongono **dati/exception**.

---

## 3) Logging ed errori
- **Niente `print()`**. Usa `logging_utils.get_structured_logger` (logger per modulo e/o per cliente).
- Non loggare **segreti** (token, credenziali, path sensibili completi).
- **Errori specifici**: solleva solo eccezioni dalla tassonomia in `exceptions.py`; **no** `except Exception` generici.
- Gli orchestratori mappano gli errori su `EXIT_CODES` in modo **deterministico**.
- Includi nei log metadati utili (`slug`, `file_path`, ecc.) via `extra={...}`.

---

## 4) I/O, sicurezza e atomicità
- Usa **`pathlib.Path`** ovunque.
- Verifica i percorsi con **`is_safe_subpath`** prima di leggere/scrivere al di fuori della sandbox cliente.
- **Scritture atomiche** (tmp + replace) per file critici; encoding **UTF‑8**.
- Non serializzare segreti su disco. Evita side‑effect non necessari.

---

## 5) Configurazioni e cache
- YAML solo con `yaml.safe_load`; fallback sicuri se chiavi mancanti.
- La regex dello **slug** è letta da `config/config.yaml` ed è **cachata** (es. `functools.lru_cache`).  
  Se un’operazione **modifica** la config, deve chiamare **`clear_slug_regex_cache()`** subito dopo.
- Le variabili d’ambiente si leggono via `env_utils`; niente accessi diretti sparsi al processo.

---

## 6) Subprocess, Docker, GitHub
- `subprocess.run([...], check=True)`; **mai** `shell=True` senza necessità.
- **Preview HonKit**: dal modulo si esegue **build/serve** senza prompt; invocazione **detached**; nessun blocco. Lo **stop** è responsabilità degli orchestratori (che lo fanno **automaticamente** a fine esecuzione).
- **Push GitHub**: centralizzato in `github_utils.py`. **Token obbligatorio** (validazione precoce). Branch da `GIT_DEFAULT_BRANCH` (fallback `main`). Non esporre PAT nei log o nelle URL.

---

## 7) Deprecation & compat
- Mantieni gli **alias deprecati** per almeno **una MINOR** dopo l’avviso (es. `--skip-push` → `--no-push`) con warning esplicito.
- Evita breaking changes negli orchestratori; se necessari, **MAJOR** con guida di migrazione.

---

## 8) Test minimi (manuali)
- Pre‑onboarding (setup locale, nessun servizio):  
  `py src/pre_onboarding.py --slug demo --non-interactive --dry-run`
- Onboarding (senza Drive, senza push):  
  `py src/onboarding_full.py --slug demo --no-drive --non-interactive`
- Onboarding con Docker attivo: verifica che la **preview parta detached** e che lo **stop avvenga automatico** in uscita.
- Push in batch:  
  `GITHUB_TOKEN=... GIT_DEFAULT_BRANCH=main py src/onboarding_full.py --slug demo --no-drive --non-interactive --push`

---

## 9) Qualità del codice
- Funzioni piccole, una responsabilità per volta.
- Evita ottimizzazioni premature; preferisci chiarezza → poi **`perf(...)`** mirati se servono.
- Commenti **sintetici** e solo dove aggiungono contesto reale.

---

### Esempi rapidi
**Logger corretto in un modulo**
```python
from pipeline.logging_utils import get_structured_logger
logger = get_structured_logger("pipeline.content_utils")

def do_work(context, file):
    # ...
    logger.info("Operazione completata", extra={"slug": context.slug, "file_path": str(file)})
```

**Errore tipizzato + mapping orchestratore**
```python
# modulo
from pipeline.exceptions import PreviewError

def preview(...):
    # ...
    raise PreviewError("Build fallita", slug=context.slug)

# orchestratore
from pipeline.exceptions import EXIT_CODES, PreviewError
try:
    preview(...)
except PreviewError:
    sys.exit(EXIT_CODES["PreviewError"])
```
