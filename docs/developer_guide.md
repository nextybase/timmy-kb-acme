# Timmy-KB - Developer Guide (v2.0.0)

Questa guida è per chi sviluppa o estende Timmy-KB: principi, setup locale, orchestratori, UI, test e regole di qualità.

> Doppio approccio: puoi lavorare da terminale (orchestratori in sequenza) oppure tramite interfaccia (Streamlit).
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Integrazione con Codex

Per velocizzare sviluppo, refactor e manutenzione del progetto puoi usare Codex come coding agent direttamente in VS Code.
L’integrazione consente di rispettare le regole definite negli `AGENTS.md` del repository e di lavorare in coerenza con i flussi NeXT, mantenendo sempre l’approccio Human‑in‑the‑Loop.
Trovi la guida completa, con configurazione e scenari d’uso, qui: [Codex Integrazione](codex_integrazione.md).

---

## Principi architetturali
- Separazione dei ruoli: orchestratori = UX/CLI e controllo flusso; moduli `pipeline/*` e `semantic/*` = logica pura senza I/O interattivo.
- Idempotenza: le operazioni possono essere ripetute senza effetti collaterali. Scritture atomiche.
- Path-safety: ogni I/O passa da SSoT (`ensure_within`, `ensure_within_and_resolve`, `sanitize_filename`).
- Configurazione esplicita: variabili d'ambiente lette tramite `ClientContext`; niente valori magici sparsi.
- Logging strutturato con redazione automatica se `LOG_REDACTION` è attivo.

Vedi anche: [Coding Rules](coding_rule.md) e [Architecture](architecture.md).

---

## Setup locale

### Requisiti
- Python >= 3.11
- (Opz.) Docker per la preview HonKit
- (Se usi Drive) JSON del Service Account e `DRIVE_ID`

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

### Variabili d'ambiente utili
- `SERVICE_ACCOUNT_FILE`: path al JSON del Service Account (Drive)
- `DRIVE_ID`: ID della cartella root su Drive
- `GITHUB_TOKEN`: token per push su GitHub (solo `onboarding_full`)
- `GIT_DEFAULT_BRANCH`, `LOG_REDACTION`, `ENV`, `CI`, `YAML_STRUCTURE_FILE`

---

## Esecuzione: orchestratori vs UI

### Orchestratori (terminal-first)
```bash
# 1) Setup locale (+ Drive opzionale)
py src/pre_onboarding.py --slug acme --name "Cliente ACME"

# 2) Tagging semantico (default: Drive)
py src/tag_onboarding.py --slug acme --proceed

# 3) Conversione + enrichment + README/SUMMARY (+ preview opz.)
py - <<PY
from pipeline.context import ClientContext
from semantic.api import convert_markdown, enrich_frontmatter, write_summary_and_readme
from semantic.vocab_loader import load_reviewed_vocab
import logging
slug = 'acme'
ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
log = logging.getLogger('semantic.manual')
convert_markdown(ctx, log, slug=slug)
# Preferisci il SSoT dei path dal contesto, evitando fallback legacy
base = ctx.base_dir
vocab = load_reviewed_vocab(base, log)
enrich_frontmatter(ctx, log, vocab, slug=slug)
write_summary_and_readme(ctx, log, slug=slug)
PY

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
```text
src/
  adapters/         # preview HonKit
  pipeline/         # path/file/log/config/github/drive utils, context, eccezioni
  semantic/         # tagging I/O, validator, enrichment
  pre_onboarding.py | tag_onboarding.py | onboarding_full.py (semantica via semantic.api)
output/timmy-kb-<slug>/{raw,book,semantic,config,logs}
```
Dettagli: [architecture.md](architecture.md).

---

## Qualità & DX
- Type-safety: preferisci firme esplicite e `Optional[...]` solo dove serve; evita `Any` nei moduli core.
- Pylance/typing: quando import opzionali possono essere `None`, usa il narrowing pattern:
  - wrapper `_require_callable(fn, name)` per funzioni opzionali;
  - controlli `if x is None: raise RuntimeError(...)` per oggetti/moduli opzionali.
- Streamlit: usa `_safe_streamlit_rerun()` (interno alla UI) per compat con stubs; evita `experimental_*` se c’è l'alternativa stabile.
- Logging: usa `get_structured_logger` quando disponibile, fallback a `logging.basicConfig` negli script.
- I/O: sempre `ensure_within_and_resolve`, `safe_write_text/bytes`.
- Naming: `to_kebab()` per cartelle RAW; slug validati con `validate_slug`.
- Path SSoT: negli esempi evita chiamate dirette a `semantic.api.get_paths`; usa `ClientContext` (`ctx.base_dir`) come fonte primaria.

---

## Testing
- Dummy dataset per smoke end-to-end:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  ```
- Smoke E2E locale (senza Drive/push): vedi `docs/test_suite.md`.
- Marker pytest: `drive`, `push`, `slow` per controllare ambito test.

### UI Streamlit — Tab Finanza (headless)
Esegue la UI in modalità headless con Playwright, crea un workspace locale coerente con `REPO_ROOT_DIR`, carica un CSV di esempio e verifica la generazione di `semantic/finance.db`.

```bash
python scripts/smoke_streamlit_finance.py
```
**Note**
- Selettori robusti su sidebar e radio “Finanza”. L’upload viene effettuato nel container del bottone *Importa in finance.db* per evitare mismatch tra rerun.
- Screenshot diagnostici salvati in temp in caso di failure.
- La UI gestisce internamente l’assenza file (bottone sempre abilitato, gating nell’handler).

#### End-to-end orchestratore (senza GitHub)
Verifica l’intera catena: pre‑onboarding → import CSV → `onboarding_full_main`, con `REPO_ROOT_DIR` isolato e push GitHub disabilitato (token rimossi dall’ambiente).

```bash
python scripts/smoke_e2e.py --slug smoke
```

---

### ClientContextProtocol (contratto condiviso)
- Riutilizza `semantic.types.ClientContextProtocol` quando una funzione richiede solo `base_dir`, `raw_dir`, `md_dir`, `slug`.
- Evita protocolli locali duplicati (`typing.Protocol`) per lo stesso scopo; mantieni un solo contratto condiviso.
- Esempi di firma consigliata:
  - `pipeline.content_utils.*(ctx: ClientContextProtocol, ...)`
  - `semantic.semantic_extractor.*(context: ClientContextProtocol, ...)`
- Quando servono campi aggiuntivi specifici (es. `config_dir`, `repo_root_dir` per mapping), definisci protocolli locali minimali separati.

### Type checking
- `make type` esegue `mypy` su `src/`.
- `make type-pyright` esegue Pyright (richiede `pyright` nel PATH oppure `npx`). Il comportamento è configurato da `pyrightconfig.json`.

---

## Path-Safety Lettura (Aggiornamento)
- Per tutte le letture di file utente (Markdown, CSV, YAML) in `pipeline/*` e `semantic/*` usa
  `pipeline.path_utils.ensure_within_and_resolve(base, p)` per ottenere un path risolto e sicuro.
- È vietato usare direttamente `open()` o `Path.read_text()` su input esterni senza passare dal wrapper.

Esempi d'uso
```python
from pipeline.path_utils import open_for_read, read_text_safe

# Lettura testo semplice (sicura)
text = read_text_safe(book_dir, md_path)

# Context manager (sicuro) per CSV/YAML/MD
with open_for_read(semantic_dir, csv_path) as f:
    rows = f.read().splitlines()
```

---

## API Semantica (Copy/CSV)

Nota: `semantic.tags_extractor.emit_tags_csv` è deprecato. Usa `semantic.api.build_tags_csv(...)` oppure il writer low-level `semantic.auto_tagger.render_tags_csv(..., base_dir=...)`.

Per evitare duplicazioni, gli orchestratori e gli script locali devono usare esclusivamente le API pubbliche in `semantic.api` per le operazioni di ingest locale e generazione CSV:

- Copia PDF locali in RAW: `semantic.api.copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger)`
- Emissione CSV dei tag grezzi: `semantic.api.build_tags_csv(context, logger, *, slug)`

Note operative
- Le funzioni applicano path‑safety e scritture atomiche; non usare helper locali o import diretti da `semantic.tags_extractor` fuori da `src/semantic/`.
- In `tag_onboarding_main` i call‑site sono già delegati a queste API.

### Writer CSV (low‑level) — Contratto `base_dir`
- Per tool/script interni che usano direttamente il writer del tagger:
  - Firma aggiornata: `semantic.auto_tagger.render_tags_csv(candidates, csv_path, *, base_dir)`
  - Path‑safety forte:
    - `safe_csv_path = ensure_within_and_resolve(base_dir, csv_path)`
    - `ensure_within(safe_csv_path.parent, safe_csv_path)`
    - Scrittura atomica con `safe_write_text(..., atomic=True)`
- Comportamento: se `csv_path` esce dal perimetro `base_dir` viene sollevata `PathTraversalError`.
- Esempio minimo:
  ```python
  from pathlib import Path
  from semantic.auto_tagger import render_tags_csv

  base = Path("output/timmy-kb-acme")
  csv_path = base / "semantic" / "tags_raw.csv"
  render_tags_csv(candidates, csv_path, base_dir=base)
  ```
- Preferenza: per orchestratori/CI usa la facade `semantic.api.build_tags_csv(...)`, che incapsula già path‑safety e side‑effects.

Pre-commit
- È presente un hook locale che impedisce l’introduzione di definizioni locali `_emit_tags_csv`/`_copy_local_pdfs_to_raw` e l’uso diretto di `semantic.tags_extractor` fuori da `src/semantic/`.
- Esegui: `pre-commit install --hook-type pre-commit --hook-type pre-push`

---

## Tabella comparativa: Orchestratori vs UI
| Aspetto             | Orchestratori (CLI)                           | UI (Streamlit)                               |
|---------------------|-----------------------------------------------|---------------------------------------------|
| Entry point         | `pre_onboarding.py`, `tag_onboarding.py`, `onboarding_full.py` | `onboarding_ui.py` con tre tab (Config, Drive, Semantica) |
| Destinatari         | Sviluppatori / run batch / CI                 | Utenti operativi / facilitatori              |
| Controllo           | Script sequenziali, parametri CLI             | Interazione step-by-step con stato UI        |
| Config              | YAML + variabili ENV                          | Editor mapping + Drive provisioning          |
| Semantica           | `semantic.api.*` invocato da script           | `semantic.api.*` invocato dalla UI           |
| Preview             | Da script `adapters/preview` (opzionale)      | Bottoni UI (start/stop container)            |
| Requisiti extra     | Token GitHub per `onboarding_full`            | Docker per preview; credenziali Drive        |
| Retrocompat         | Mirroring mapping YAML (in `pre_onboarding`)  | Mapping YAML solo come input storico         |

---

> Versione: 1.9.2 (2025-09-19)
> Stato: Allineata al codice corrente; esempi aggiornati a `ClientContext` come SSoT dei path; aggiunte sezioni di Smoke testing (UI Streamlit & E2E).

## Security and Compliance

- Esegui `make sbom` per generare SBOM CycloneDX (stampa `sbom.json`).
- Il target usa `tools/sbom.sh`; assicurati che `cyclonedx-py` (cyclonedx-bom) sia installato nel venv.
- Secret scanning: `pre-commit run gitleaks --all-files` utilizza `.gitleaks.toml` come configurazione minima.
