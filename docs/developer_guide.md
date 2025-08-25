# Developer Guide — Timmy-KB (v1.2.2)

Questa guida è rivolta agli sviluppatori e documenta le scelte architetturali e i principi di base adottati per garantire **coerenza, testabilità e robustezza** della pipeline.  
È il documento di riferimento per chi sviluppa nuovo codice: ogni implementazione deve rifarsi a questa guida, alla descrizione dell’architettura e mantenere sempre compatibilità locale e riuso delle funzioni già presenti, proponendone l’eventuale aggiornamento solo se necessario.

---

## 1) Policy di redazione log centralizzata

### Obiettivo
Assicurare che i dati sensibili (token, credenziali, ID) non vengano mai scritti in chiaro nei log, con una logica uniforme in tutta la pipeline.

### Fonte di verità
`src/pipeline/env_utils.py::compute_redact_flag(env, log_level)`

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

### Compatibilità
- **API chiara**: la firma di `ClientContext.load(...)` è stabile e documentata.
- **Log consistenti**: i messaggi sono strutturati e uniformi.
- **No prompt**: nessuna interazione diretta in `context.py`.

---

## 3) Orchestratori vs Moduli

### Obiettivo
Stabilire responsabilità chiare e ridurre ambiguità tra orchestratori e moduli tecnici.

### Linee guida
- Orchestratori (`pre_onboarding.py`, `tag_onboarding.py`, `semantic_onboarding.py`, `onboarding_full.py`) = UX (CLI, prompt, exit codes).
- Moduli (`pipeline/*`, `semantic/*`, `adapters/*`) = logica tecnica. Niente `sys.exit()`, niente `input()`.
- Variabili d’ambiente critiche centralizzate in `env_utils.py`.
- Conversione RAW→BOOK solo in locale; Drive usato solo in pre-onboarding.
- Validazione slug tramite `path_utils.ensure_valid_slug` (SSoT).
- **Adapter coerenti (PR-4)**: firma `(context, logger, **opts)`.

---

## 4) Path-safety e scritture atomiche

- **SSoT**: `ensure_within` vive in `pipeline.path_utils`.
- Ogni scrittura deve usare `safe_write_text/bytes` con `atomic=True`.
- Config critici (`config.yaml`) salvati con backup `.bak`.
- Vietato salvare segreti su disco.

---

## 5) Test suggeriti

### Obiettivo
Assicurare stabilità e robustezza dopo modifiche.

### Casi consigliati
- **Matrix redazione**: `{LOG_REDACTION ∈ [auto,on,off]} × {ENV ∈ [dev,prod,ci]} × {CI ∈ [0,1]} × {log_level ∈ [DEBUG,INFO]}`.
- **Bootstrap paths**: assenza di `config/config.yaml` → creazione da template.
- **Safe-load YAML**: file vuoto/non valido → `ConfigError` coerente.
- **Drive idempotente**: stessa struttura non deve duplicare cartelle.
- **Conversione RAW→BOOK**: solo PDF in `raw/` generano Markdown.
- **Frontmatter enrichment**: test con `tags_raw.csv` vuoto/parziale/completo.
- **Fallback README/SUMMARY**: testare idempotenza di `ensure_readme_summary`.
- **Preview Docker**: `start_preview/stop_preview` loggano correttamente.
- **Push GitHub**: richiede `GITHUB_TOKEN`; testare errore se assente.
- **Dummy pipeline**: `gen_dummy_kb.py` + `tests/test_dummy_pipeline.py` validano coerenza CSV↔PDF e stub semantici.

---

## 6) Policy di coerenza doc/codice

- Aggiornare **README** e **User Guide** (UX/CLI).
- Aggiornare **Developer Guide**, **Architecture**, **Coding Rules**.
- Allineare **CHANGELOG** e tag SemVer.

---

## 7) Principi fondanti

- **Modularità**: orchestratori separati dalla logica.
- **Idempotenza**: operazioni ripetibili senza effetti collaterali.
- **Separazione UX/Logica**: CLI/exit negli orchestratori, logica nei moduli.
- **Centralizzazione ENV e log**: gestione in `env_utils`, redazione uniforme.
- **Scritture sicure**: `ensure_within` + `safe_write_*`.
- **Testabilità**: funzioni pure, dipendenze iniettate.
- **Trasparenza**: log strutturati con `run_id`.
- **Consistenza API**: firme uniformi per orchestratori e adapter.
- **Compatibilità cross-platform**: garantire che path e encoding funzionino anche su Windows.

---

