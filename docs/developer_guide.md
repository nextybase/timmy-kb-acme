# Developer Guide — Timmy-KB (v1.2.0)

Questa guida è rivolta agli sviluppatori e documenta le scelte architetturali e i principi di base adottati per garantire **coerenza, testabilità e robustezza** della pipeline.  
È il documento di riferimento per chi sviluppa nuovo codice: ogni implementazione deve rifarsi a questa guida, alla descrizione dell’architettura e mantenere sempre compatibilità locale e riuso delle funzioni già presenti, proponendone l’eventuale aggiornamento solo se necessario.

---

## 1) Policy di redazione log centralizzata

### Obiettivo
Assicurare che i dati sensibili (token, credenziali, ID) non vengano mai scritti in chiaro nei log, con una logica uniforme in tutta la pipeline.

### Fonte di verità
`src/pipeline/env_utils.py::compute_redact_flag(env, log_level)`

### Firma
```py
compute_redact_flag(env: Mapping[str, Any], log_level: str = "INFO") -> bool
```

### Regole
- `LOG_REDACTION = on | always | true` → **ON**
- `LOG_REDACTION = off | never | false` → **OFF**
- `LOG_REDACTION = auto` (default) → **ON** se almeno una delle seguenti condizioni è vera:
  - `ENV ∈ {prod, production, ci}`
  - `CI = true`
  - esistono credenziali sensibili (`GITHUB_TOKEN`, `SERVICE_ACCOUNT_FILE`)
  - altrimenti → **OFF**
- `log_level = DEBUG` forza sempre **OFF**.

---

## 2) Strutturazione di `ClientContext.load`

### Obiettivo
Mantenere un punto di ingresso unico, chiaro e modulare per inizializzare la pipeline, riducendo la complessità e favorendo i test.

### Fonte di verità
`src/pipeline/context.py`

### Helper interni
- `_init_logger(logger, run_id)` → logger strutturato
- `_init_paths(slug, logger)` → percorsi base e `config.yaml`
- `_load_yaml_config(config_path, logger)` → caricamento sicuro YAML
- `_load_env(require_env=...)` → raccolta variabili ambiente
- `compute_redact_flag(env, log_level)` → calcolo flag redazione

### Pseudocodice
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
- **API chiara**: la firma di `ClientContext.load(...)` è stabile e documentata.
- **Log consistenti**: i messaggi sono strutturati e uniformi.
- **No prompt**: come regola, nessuna interazione diretta in `context.py`.

---

## 3) Refactor orchestratori

### Obiettivo
Stabilire responsabilità chiare e ridurre ambiguità tra orchestratori e moduli tecnici.

### Linee guida
- Gli orchestratori (`pre_onboarding.py`, `tag_onboarding.py`, `onboarding_full.py`) sono responsabili **solo** di UX (prompt, parsing CLI, exit codes).
- I moduli di pipeline gestiscono la logica tecnica e non devono chiamare `sys.exit()` né `input()`.
- Tutte le variabili di ambiente critiche sono centralizzate in `env_utils.py`.
- La creazione cartelle Drive è gestita unicamente in `src/pipeline/drive/` con idempotenza garantita.
- Conversione RAW → BOOK avviene solo in locale; Drive è usato solo in fase di pre-onboarding.
- La validazione dello **slug** è disponibile come helper dedicato in `path_utils.ensure_valid_slug`, da usare in caso di necessità per evitare duplicazioni.
- **Adapter coerenti (PR-4)**: tutti gli adapter esposti hanno firma `(context, logger, **opts)` o variante coerente.

---

## 4) Test suggeriti

### Obiettivo
Assicurare che la pipeline rimanga stabile, robusta e prevedibile anche dopo modifiche.

### Casi consigliati
- **Matrix redazione**: `{LOG_REDACTION ∈ [auto,on,off]} × {ENV ∈ [dev,prod,production,ci]} × {CI ∈ [0,1]} × {log_level ∈ [DEBUG,INFO]}`.
- **Bootstrap paths**: assenza di `output/timmy-kb-<slug>/config/config.yaml` → creazione da template.
- **Safe-load YAML**: file vuoto/non presente → solleva `ConfigError` coerente.
- **Drive idempotente**: ricreazione della stessa struttura non deve duplicare cartelle.
- **Conversione RAW → BOOK**: verifica che solo i PDF in `raw/` generino Markdown.
- **Frontmatter enrichment**: test con `tags.yaml` vuoto, parziale, completo.
- **Fallback README/SUMMARY**: verificare che `adapters.content_fallbacks.ensure_readme_summary` scriva in modo idempotente.
- **Preview Docker**: test su `adapters.preview.start_preview/stop_preview`, verifica coerenza parametri e log.

---

## 5) Policy di coerenza doc/codice

### Obiettivo
Mantenere sincronizzati codice e documentazione in ogni rilascio.

### Regole
- Aggiornamento README e User Guide (per UX/CLI).
- Aggiornamento Developer Guide (per refactor e scelte interne).
- Aggiornamento Architecture e Coding Rules (per invarianti e regole operative).
- Allineamento CHANGELOG.

---

## 6) Principi fondanti per sviluppatori

### Obiettivo
Fornire linee guida generali per garantire robustezza e coerenza dello sviluppo.

### Principi
- **Modularità**: responsabilità incapsulate in moduli dedicati, orchestratori separati dalla logica.
- **Idempotenza**: operazioni ripetibili senza effetti collaterali (Drive, conversione RAW → BOOK).
- **Separazione UX/Logica**: orchestratori = interazione/uscita; moduli = logica tecnica.
- **Centralizzazione ENV e log**: variabili critiche in `env_utils`, redazione log uniforme.
- **Scritture sicure**: usare sempre `safe_write_text`/`safe_write_bytes` con `ensure_within`.
- **Testabilità**: funzioni pure e helper interni per ridurre complessità.
- **Trasparenza**: log strutturati e tracciabilità completa.
- **Consistenza API**: firme uniformi per orchestratori e adapter; nessun side-effect fuori da scritture atomiche.

---

