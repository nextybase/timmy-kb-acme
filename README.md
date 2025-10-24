# Timmy KB — README (v1.0 Beta)

Pipeline per generare una Knowledge Base Markdown AI‑ready a partire dai PDF del cliente, con arricchimento semantico, anteprima locale (HonKit via Docker) e push opzionale su GitHub.

---

## Prerequisiti

- Python ≥ 3.11
- Docker (solo per la preview)
- Credenziali Google Drive (Service Account JSON) se usi la sorgente Drive per il tagging
- (Opz.) `GITHUB_TOKEN` per il push

### Variabili d’ambiente (principali)
- `SERVICE_ACCOUNT_FILE` – JSON del Service Account (Drive)
- `DRIVE_ID` – ID cartella root dello spazio Drive (RAW parent)
- `GITHUB_TOKEN` – richiesto per il push GitHub
- `GIT_DEFAULT_BRANCH` – branch di default (es. `main`)
- `OPENAI_API_KEY` o `OPENAI_API_KEY_FOLDER`
- `YAML_STRUCTURE_FILE` – opzionale (default `config/cartelle_raw.yaml`)
- `LOG_REDACTION` – `auto` (default) | `on` | `off`
- `ENV`, `CI`

---

## Gestione dipendenze (SSoT con pip‑tools)

Installazione con pin generati da `pip-compile`:

```bash
# Runtime
pip install -r requirements.txt

# Dev/Test (include runtime + toolchain)
pip install -r requirements-dev.txt

# Opzionali (NLP/RAG, integrazioni)
pip install -r requirements-optional.txt
```

Aggiornare i pin modificando i file `*.in` e rigenerando:

```bash
pip-compile requirements.in
pip-compile requirements-dev.in
pip-compile requirements-optional.in
# constraints.txt viene rigenerato da requirements.in
```

> Alternativa “extras” (per ambienti non pin‑locked):
> `pip install .[drive]` oppure, in sviluppo, `pip install -e ".[drive]"`.

---

## Onboarding: flusso end‑to‑end

1. **Pre‑onboarding**
   Crea la struttura locale (e opzionale remota su Drive), copia i template semantici, genera `config.yaml`.

2. **Tag Onboarding (HiTL)**
   Default sorgente = **Drive**: scarica PDF dalla cartella RAW su Drive e genera `semantic/tags_raw.csv`. Dopo checkpoint umano produce `README_TAGGING.md` e `tags_reviewed.yaml`.

3. **Semantic Onboarding**
   Converte i PDF in `book/*.md`, arricchisce i frontmatter dai tag canonici (`semantic/tags.db`), genera `README.md` e `SUMMARY.md`. (Opz.) avvia la preview Docker (HonKit).

4. **Onboarding Full (Push)**
   Preflight su `book/` (solo `.md`), garantisce `README.md` e `SUMMARY.md`, push su GitHub via `GITHUB_TOKEN`.

---

## Modalità d’uso

### Interattiva (prompt guidati)

```bash
py src/pre_onboarding.py
py src/tag_onboarding.py
py - <<PY
from semantic.api import convert_markdown, enrich_frontmatter, write_summary_and_readme
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger

slug = "acme"
ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
log = get_structured_logger("semantic.manual")

convert_markdown(ctx, log, slug=slug)
from semantic.vocab_loader import load_reviewed_vocab
vocab = load_reviewed_vocab(ctx.base_dir, log)
enrich_frontmatter(ctx, log, vocab, slug=slug)
write_summary_and_readme(ctx, log, slug=slug)
PY
py src/onboarding_full.py
```

### CLI / Batch (senza prompt)

```bash
py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive
py src/tag_onboarding.py --slug acme --non-interactive --proceed
py src/semantic_onboarding.py --slug acme --non-interactive
py src/onboarding_full.py --slug acme --non-interactive
```

### Interfaccia (Streamlit)

```bash
streamlit run onboarding_ui.py
```
Requisito: Streamlit ≥ 1.50. Guida: `docs/guida_ui.md`.

---

## Struttura output per cliente

```
output/
  timmy-kb-<slug>/
    raw/      # PDF caricati/scaricati
    book/     # Markdown + SUMMARY.md + README.md
    semantic/ # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml, vision_statement.txt, tags.db, finance.db (opz.)
    config/   # config.yaml (aggiornato con eventuali ID Drive)
    logs/     # log centralizzati (pre_onboarding, tag_onboarding, onboarding_full)
```

> Lo slug deve essere valido secondo le regole in `config/config.yaml`.

---

## Vision Statement → YAML

```bash
py src/tools/gen_vision_yaml.py --slug <slug>
```
- Input: `VisionStatement.pdf` (in `config/`, `raw/` o `config/` globale del repo)
- Output: `semantic/semantic_mapping.yaml` e `semantic/vision_statement.txt`
- Richiede `OPENAI_API_KEY` o `OPENAI_API_KEY_FOLDER`.

---

## Logging, sicurezza, exit codes

- **Logging centralizzato** in `output/timmy-kb-<slug>/logs/`, con `run_id` e redazione automatica dei segreti.
- **Path‑safety** enforced e scritture **atomiche** per ogni I/O di repo/sandbox.
- Exit codes (principali): `0` OK; `2` ConfigError; `30` PreviewError; `40` PushError.

_Esempio logger_

```python
from pipeline.logging_utils import get_structured_logger
log = get_structured_logger(__name__, run_id=None, context={"slug": "acme"})
log.info("semantic.index.start", extra={"slug": "acme"})
```

---

## Preflight UI

La UI verifica `.env` e librerie; degrada in modo sicuro se Docker non è presente e nasconde il box *Prerequisiti* quando tutto è OK.

---

## Impostazioni retriever (UI)

Configurabili dalla sidebar; salvate in `config.yaml` alla chiave `retriever`.

```yaml
retriever:
  candidate_limit: 4000
  latency_budget_ms: 300
  auto_by_budget: false
```

---

## Drive: installazione (extras)

```bash
pip install .[drive]
# sviluppo
pip install -e ".[drive]"
```

Per ambienti pin‑locked, usa i `requirements‑optional(.in/.txt)` rigenerati con pip‑tools.

---

## QA locale

Hook pre‑commit e comandi rapidi:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
make qa-safe     # isort/black/ruff/mypy (se presenti)
make ci-safe     # qa-safe + pytest
pytest -ra       # dopo aver generato il dataset dummy
```

---

## Ingest/CSV — Best practice

Usa le API pubbliche in `semantic.api` per copiare PDF e generare `tags_raw.csv`; evita helper interni non pubblici.

---

## Note operative

- La preview richiede Docker; se assente viene saltata.
- Nel push GitHub vengono inclusi solo i `.md` in `book/`.
- Per scenari air‑gapped: `--source=local` e popolamento manuale di `raw/`.
