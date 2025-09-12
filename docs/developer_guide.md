# Timmy-KB - Developer Guide (v1.8.1)

Questa guida Ã¨ per chi sviluppa o estende Timmy-KB: principi, setup locale, orchestratori, UI, test e regole di qualitÃ .

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
> Avvio interfaccia: `streamlit run onboarding_ui.py` â€” vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Integrazione con Codex

Per velocizzare sviluppo, refactor e manutenzione del progetto puoi usare **Codex** come coding agent direttamente in VS Code.
Lâ€™integrazione consente di rispettare le regole definite negli `AGENTS.md` del repository e di lavorare in coerenza con i flussi NeXT, mantenendo sempre lâ€™approccio Human-in-the-Loop.
Trovi la guida completa, con configurazione e scenari dâ€™uso, qui: [Codex Integrazione](codex_integrazione.md).

---

## Principi architetturali
- **Separazione dei ruoli**: orchestratori = UX/CLI e controllo flusso; moduli `pipeline/*` e `semantic/*` = logica pura senza I/O interattivo.
- **Idempotenza**: le operazioni possono essere ripetute senza effetti collaterali. Scritture **atomiche**.
- **Path-safety**: ogni I/O passa da SSoT (`ensure_within`, `sanitize_filename`).
- **Configurazione esplicita**: variabili d'ambiente lette tramite `ClientContext`; niente valori magici sparsi.
- **Logging strutturato** con redazione automatica se `LOG_REDACTION` Ã¨ attivo.

Vedi anche: [Coding Rules](coding_rule.md) e [Architecture](architecture.md).

---

## Setup locale

### Requisiti
- **Python >= 3.11**
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
Esempio headless via semantic.api (consigliato):
py - <<PY
from semantic.api import get_paths, convert_markdown, enrich_frontmatter, write_summary_and_readme
from pipeline.context import ClientContext
import logging
slug = 'acme'
ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
log = logging.getLogger('semantic.manual')
convert_markdown(ctx, log, slug=slug)
base = get_paths(slug)['base']
from semantic.vocab_loader import load_reviewed_vocab
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

Nota API: la UI importa le funzioni semantiche dalla facade pubblica `semantic.api` (non dagli underscore di `semantic_onboarding`). Gli orchestratori CLI restano invariati.

---

## Struttura progetto (promemoria)
```
src/
  adapters/         # preview HonKit, fallback contenuti
  pipeline/         # path/file/log/config/github/drive utils, context, eccezioni
  semantic/         # tagging I/O, validator, enrichment
  pre_onboarding.py | tag_onboarding.py | onboarding_full.py (semantica via semantic.api)
output/timmy-kb-<slug>/{raw,book,semantic,config,logs}
```
Dettagli: [architecture.md](architecture.md).

---

## QualitÃ  & DX
- **Type-safety**: preferisci firme esplicite e `Optional[...]` solo dove serve; evita `Any` nei moduli core.
- **Pylance/typing**: quando import opzionali possono essere `None`, usa il *narrowing* pattern:
  - wrapper `_require_callable(fn, name)` per funzioni opzionali;
  - controlli `if x is None: raise RuntimeError(...)` per oggetti/moduli opzionali.
- **Streamlit**: usa `_safe_streamlit_rerun()` (interno alla UI) per compat con stubs; evita `experimental_*` se câ€™Ã¨ l'alternativa stabile.
- **Logging**: usa `get_structured_logger` quando disponibile, fallback a `logging.basicConfig` negli script.
- **I/O**: sempre `ensure_within_and_resolve`, `safe_write_text/bytes`.
- **Naming**: `to_kebab()` per cartelle RAW; slug validati con `validate_slug`.

---

## Testing
- **Dummy dataset** per smoke end-to-end:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  pytest -ra
  ```
- I test non richiedono credenziali reali (Drive/Git mockati).
- Verifica invarianti: solo `.md` in `book/`; `README.md`/`SUMMARY.md` sempre presenti.
- Windows/Linux supportati; occhio a path POSIX nei CSV.

---

## Drive & sicurezza
- Non inserire credenziali nel repo; usa file JSON localmente e variabili d'ambiente.
- Ogni upload/download passa tramite le API alto livello in `pipeline/drive_utils.py`.
- Per il download via UI Ã¨ esposta `config_ui.drive_runner.download_raw_from_drive` (scritture atomiche, path-safety).

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
- Evita duplicazioni: riusa utilitÃ  esistenti (SSoT) prima di introdurne di nuove.

---

## SSoT dei contratti e type checking

### `ClientContextProtocol` (contratto condiviso)
- Riutilizza `semantic.types.ClientContextProtocol` quando una funzione richiede solo `base_dir`, `raw_dir`, `md_dir`, `slug`.
- Evita protocolli locali duplicati (`typing.Protocol`) per lo stesso scopo; mantieni un solo contratto condiviso.
- Esempi di firma consigliata:
  - `pipeline.content_utils.*(ctx: ClientContextProtocol, ...)`
  - `semantic.semantic_extractor.*(context: ClientContextProtocol, ...)`
- Quando servono campi aggiuntivi specifici (es. `config_dir`, `repo_root_dir` per mapping), definisci protocolli locali minimali separati.

### Type checking
- `make type` esegue `mypy` su `src/`.
- `make type-pyright` esegue Pyright (richiede `pyright` nel PATH oppure `npx`). Il comportamento Ã¨ configurato da `pyrightconfig.json`.


---

## Path-Safety Lettura (Aggiornamento)
- Per tutte le letture di file utente (Markdown, CSV, YAML) in pipeline/* e semantic/* usa
  pipeline.path_utils.ensure_within_and_resolve(base, p) per ottenere un path risolto e sicuro.
- È vietato usare direttamente open() o Path.read_text() su input esterni senza passare dal wrapper.

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

## Helper di fallback per Markdown

In `semantic.api` è disponibile l'helper interno:

- `_fallback_markdown_from_raw(raw_dir: Path, book_dir: Path) -> list[Path]`

Scopo e comportamento:
- Viene usato automaticamente da `convert_markdown(...)` quando le utilità di conversione
  avanzata non sono disponibili (ad es. `_convert_md is None`).
- Per ogni sottocartella di primo livello in `raw_dir` genera un file Markdown
  placeholder `<nome>.md` in `book_dir` con:
  - titolo derivato dal nome cartella (normalizzato rimuovendo `_-/` consecutivi);
  - contenuto placeholder: `# <Titolo>\n\n(Contenuti da <cartella>/)\n`.
- Applica path‑safety SSoT: valida ogni destinazione con `ensure_within(book_dir, md_file)`
  e scrive con `safe_write_text(..., atomic=True)`.
- Ritorna la lista dei `.md` presenti in `book_dir`, ordinata tramite `sorted_paths(..., base=book_dir)`.

Esempio d’uso diretto (solo per test/local tooling):
```python
from pathlib import Path
from semantic.api import _fallback_markdown_from_raw

raw = Path('output/timmy-kb-acme/raw')
book = Path('output/timmy-kb-acme/book')
mds = _fallback_markdown_from_raw(raw, book)
for p in mds:
    print(p.name)
```

---

## API Semantica (Copy/CSV)

Per evitare duplicazioni, gli orchestratori e gli script locali devono usare esclusivamente le API pubbliche in `semantic.api` per le operazioni di ingest locale e generazione CSV:

- Copia PDF locali in RAW: `semantic.api.copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger)`
- Emissione CSV dei tag grezzi: `semantic.api.build_tags_csv(context, logger, *, slug)`

Note operative
- Le funzioni applicano path‑safety e scritture atomiche; non usare helper locali o import diretti da `semantic.tags_extractor` fuori da `src/semantic/`.
- In `tag_onboarding_main` i call‑site sono già delegati a queste API.

Pre-commit
- È presente un hook locale che impedisce l’introduzione di definizioni locali `_emit_tags_csv`/`_copy_local_pdfs_to_raw` e l’uso diretto di `semantic.tags_extractor` fuori da `src/semantic/`.
- Esegui: `pre-commit install --hook-type pre-commit --hook-type pre-push`
