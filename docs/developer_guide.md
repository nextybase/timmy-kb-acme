# Timmy‑KB — Developer Guide (v1.6.0)

Questa guida è per chi sviluppa o estende Timmy‑KB: principi, setup locale, orchestratori, UI, test e regole di qualità.

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.  
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Principi architetturali
- **Separazione dei ruoli**: orchestratori = UX/CLI e controllo flusso; moduli `pipeline/*` e `semantic/*` = logica pura senza I/O interattivo.
- **Idempotenza**: le operazioni possono essere ripetute senza effetti collaterali. Scritture **atomiche**.
- **Path‑safety**: ogni I/O passa da SSoT (`ensure_within`, `sanitize_filename`).
- **Configurazione esplicita**: variabili d’ambiente lette tramite `ClientContext`; niente valori magici sparsi.
- **Logging strutturato** con redazione automatica se `LOG_REDACTION` è attivo.

Vedi anche: [Coding Rules](coding_rules.md) e [Architecture](architecture.md).

---

## Setup locale

### Requisiti
- **Python ≥ 3.10**
- (Opz.) **Docker** per la preview HonKit
- (Se usi Drive) JSON del **Service Account** e `DRIVE_ID`

### Ambiente virtuale
```bash
# Windows
py -m venv venv
venv\Scripts\activate
pip install -U pip wheel
pip install -r requirements.txt

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
```

### Variabili d’ambiente utili
- `SERVICE_ACCOUNT_FILE` → path al JSON del Service Account (Drive)
- `DRIVE_ID` → ID della cartella root su Drive
- `GITHUB_TOKEN` → token per push su GitHub (solo `onboarding_full`)
- `GIT_DEFAULT_BRANCH`, `LOG_REDACTION`, `ENV`, `CI`, `YAML_STRUCTURE_FILE`

---

## Esecuzione: orchestratori vs UI

### Orchestratori (terminal‑first)
```bash
# 1) Setup locale (+ Drive opzionale)
py src/pre_onboarding.py --slug acme --name "Cliente ACME"

# 2) Tagging semantico (default: Drive)
py src/tag_onboarding.py --slug acme --proceed

# 3) Conversione + enrichment + README/SUMMARY (+ preview opz.)
py src/semantic_onboarding.py --slug acme --no-preview

# 4) Push finale (se richiesto)
py src/onboarding_full.py --slug acme
```
Aggiungi `--non-interactive` per i run batch/CI.

### Interfaccia (UI)
```bash
streamlit run onboarding_ui.py
```
Guida completa: [docs/guida_ui.md](guida_ui.md).

---

## Struttura progetto (promemoria)
```
src/
  adapters/         # preview HonKit, fallback contenuti
  pipeline/         # path/file/log/config/github/drive utils, context, eccezioni
  semantic/         # tagging I/O, validator, enrichment
  pre_onboarding.py | tag_onboarding.py | semantic_onboarding.py | onboarding_full.py
output/timmy-kb-<slug>/{raw,book,semantic,config,logs}
```
Dettagli: [architecture.md](architecture.md).

---

## Qualità & DX
- **Type‑safety**: preferisci firme esplicite e `Optional[...]` solo dove serve; evita `Any` nei moduli core.
- **Pylance/typing**: quando import opzionali possono essere `None`, usa il *narrowing* pattern:
  - wrapper `_require_callable(fn, name)` per funzioni opzionali;
  - controlli `if x is None: raise RuntimeError(...)` per oggetti/moduli opzionali.
- **Streamlit**: usa `_safe_streamlit_rerun()` (interno alla UI) per compat con stubs; evita `experimental_*` se c’è l’alternativa stabile.
- **Logging**: usa `get_structured_logger` quando disponibile, fallback a `logging.basicConfig` negli script.
- **I/O**: sempre `ensure_within_and_resolve`, `safe_write_text/bytes`.
- **Naming**: `to_kebab()` per cartelle RAW; slug validati con `validate_slug`.

---

## Testing
- **Dummy dataset** per smoke end‑to‑end:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  pytest -ra
  ```
- I test non richiedono credenziali reali (Drive/Git mockati).  
- Verifica invarianti: solo `.md` in `book/`; `README.md`/`SUMMARY.md` sempre presenti.
- Windows/Linux supportati; occhio a path POSIX nei CSV.

---

## Drive & sicurezza
- Non inserire credenziali nel repo; usa file JSON localmente e variabili d’ambiente.
- Ogni upload/download passa tramite le API alto livello in `pipeline/drive_utils.py`.
- Per il download via UI è esposta `config_ui.drive_runner.download_raw_from_drive` (scritture atomiche, path‑safety).

---

## Release & versioning
- Modello: **SemVer** + `CHANGELOG.md` (Keep a Changelog).
- Chiusura release: aggiorna `CHANGELOG.md`, `README.md`, documenti in `docs/` e bump di versione nei punti visibili.
- Tag e branch: vedi [versioning_policy.md](versioning_policy.md).

---

## Contributi
- Pull request piccole, atomic commit, messaggi chiari.  
- Aggiungi/aggiorna i test quando modifichi comportamenti.  
- Mantieni la documentazione allineata (README + docs/).  
- Evita duplicazioni: riusa utilità esistenti (SSoT) prima di introdurne di nuove.

