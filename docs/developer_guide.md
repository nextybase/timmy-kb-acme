# Developer Guide — Fase 1 (Refactor interno, nessun cambio di comportamento)

Questa sezione descrive le modifiche **interne** introdotte in Fase 1 per migliorare testabilità e chiarezza del codice, **senza modificare** UX, API pubbliche o flussi della pipeline.

---

## 1) Policy di redazione log centralizzata

**Fonte di verità:** `src/pipeline/env_utils.py::compute_redact_flag(env, log_level)`

### Firma
```py
compute_redact_flag(env: Mapping[str, Any], log_level: str = "INFO") -> bool
```

### Regole
- `LOG_REDACTION = on | always | true` → **ON**
- `LOG_REDACTION = off | never | false` → **OFF**
- `LOG_REDACTION = auto` (default) → **ON** se **una** delle seguenti è vera:
  - `ENV ∈ {prod, production, ci}`
  - `CI = true`
  - presenti credenziali sensibili (`GITHUB_TOKEN` **o** `SERVICE_ACCOUNT_FILE`)
  - altrimenti **OFF**
- `log_level = DEBUG` forza **OFF** (debug locale).

> `is_log_redaction_enabled(context)` è mantenuta per **retro‑compatibilità**, ma è **deprecated**: usa sempre `compute_redact_flag` per nuova logica.

---

## 2) Strutturazione di `ClientContext.load`

**Fonte di verità:** `src/pipeline/context.py`

`ClientContext.load(...)` delega ora a **helper interni** (stesso file) per ridurre la complessità ciclomatica e rendere i passi testabili in isolamento:

- `_init_logger(logger, run_id)` → inizializza/riusa il logger strutturato
- `_init_paths(slug, logger)` → calcola percorsi e garantisce `config.yaml` (bootstrap da template)
- `_load_yaml_config(config_path, logger)` → carica la configurazione cliente (safe‑load)
- `_load_env(require_env=...)` → raccoglie variabili d’ambiente (richieste/opzionali)
- `compute_redact_flag(env, log_level)` → calcola il flag di redazione (nessun side‑effect)

### Sequenza (pseudocodice)

```py
logger = _init_logger(logger, run_id)
validate_slug(slug)
base_dir, config_path = _init_paths(slug, logger)
settings = _load_yaml_config(config_path, logger)
env_vars = _load_env(require_env=require_env)
log_level = (kwargs.get("log_level") or "INFO").upper()
redact = compute_redact_flag(env_vars, log_level)
return ClientContext(..., logger=logger, env=env_vars, settings=settings, redact_logs=redact, ...)
```

### Compatibilità
- **API invariata**: firma di `ClientContext.load(...)` e dei campi `ClientContext` non cambia.
- **Log invariati**: messaggi e campi strutturati restano uguali; cambia solo l’organizzazione interna.
- **No prompt**: come prima, nessuna interazione con l’utente in `context.py`.

---

## 3) Test suggeriti

- **Matrix redazione**: `{LOG_REDACTION ∈ [auto,on,off]} × {ENV ∈ [dev,prod,production,ci]} × {CI ∈ [0,1]} × {log_level ∈ [DEBUG,INFO]}`  
  Assicurarsi che `compute_redact_flag` produca il valore atteso.
- **Bootstrap paths**: assenza di `output/timmy-kb-<slug>/config/config.yaml` → creazione da template.
- **Safe‑load YAML**: file vuoto o non presente → comportamento coerente (errori mappati in `ConfigError`).

---

## 4) Deprecation note

- `is_log_redaction_enabled(context)` resta disponibile per chiamanti legacy, ma tutta la pipeline deve progressivamente migrare a `compute_redact_flag(env, log_level)`.
