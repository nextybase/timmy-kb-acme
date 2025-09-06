# Timmy KB - README (v1.7.0)

Pipeline per la generazione di una Knowledge Base Markdown AI-ready a partire da PDF cliente, con arricchimento semantico, anteprima HonKit (Docker) e push opzionale su GitHub.

---

# Timmy KB Onboarding

Pipeline di onboarding dei clienti per Timmy KB.

## Flusso principale
1. Pre-Onboarding  
   Crea la struttura locale, opzionalmente quella remota su Drive, copia i template semantici e genera `config.yaml`.

2. Tag Onboarding (HiTL)  
   Default: Google Drive — scarica i PDF dalla cartella RAW su Drive e genera `semantic/tags_raw.csv`.  
   Dopo il checkpoint umano produce `README_TAGGING.md` e `tags_reviewed.yaml`.

3. Semantic Onboarding  
   Converte i PDF in `book/*.md`, arricchisce i frontmatter leggendo i tag canonici dal DB SQLite (`semantic/tags.db`, migrato dallo YAML storico se presente), genera `README.md` e `SUMMARY.md`, e può avviare la preview Docker (HonKit).

4. Onboarding Full (Push)  
   Verifica che in `book/` ci siano solo `.md` (i `.md.fp` vengono ignorati), garantisce i fallback README/SUMMARY e pubblica su GitHub.

> SSoT dei tag: la fonte unica è il DB SQLite (`semantic/tags.db`); lo YAML storico (`tags_reviewed.yaml`) resta come input per migrazione/authoring.

---

## Prerequisiti

- Python >= 3.11
- Docker (per la preview)
- Credenziali Google Drive (Service Account JSON) — necessarie per il default di `tag_onboarding` (Drive)
- (Opz.) GitHub Token (`GITHUB_TOKEN`) per il push

### Variabili d'ambiente

- `SERVICE_ACCOUNT_FILE`: path al JSON del Service Account (Drive)  
- `DRIVE_ID`: ID cartella root dello spazio Drive (RAW parent)  
- `GITHUB_TOKEN`: richiesto per il push GitHub  
- `GIT_DEFAULT_BRANCH`: branch di default (fallback `main`)  
- `YAML_STRUCTURE_FILE`: override opzionale del file YAML per il pre-onboarding (default `config/cartelle_raw.yaml`)  
- `LOG_REDACTION`: `auto` (default), `on`, `off`  
- `ENV`, `CI`: modalità operative

---

## Struttura output per cliente

```
output/
  timmy-kb-<slug>/
    raw/      # PDF caricati/scaricati
    book/     # Markdown + SUMMARY.md + README.md
    semantic/ # cartelle_raw.yaml, semantic_mapping.yaml, tags_raw.csv, tags_reviewed.yaml, tags.db, finance.db (opz.)
    config/   # config.yaml (aggiornato con eventuali ID Drive)
    logs/     # log centralizzati (pre_onboarding, tag_onboarding, onboarding_full)
```

> Lo slug deve rispettare le regole in `config/config.yaml`. In interattivo, se non valido, viene richiesto di correggerlo.

---

## Modalità d'uso

> Doppio approccio: puoi lavorare da terminale usando gli orchestratori in sequenza oppure tramite interfaccia (Streamlit).

### Interattiva (prompt guidati)
```bash
py src/pre_onboarding.py
py src/tag_onboarding.py
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
py src/onboarding_full.py
```

### CLI / Batch (senza prompt)
```bash
py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive
py src/tag_onboarding.py --slug acme --non-interactive --proceed             # default: Drive
Rem: per flussi CLI, usare direttamente semantic.api come da snippet sopra.
py src/onboarding_full.py --slug acme --non-interactive
```

### Interfaccia (Streamlit)
L'alternativa agli orchestratori via terminale è l'interfaccia.

Avvio:
```bash
streamlit run onboarding_ui.py
```
Guida completa: `docs/guida_ui.md`.

---

## 1) Pre-onboarding

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome>] [--non-interactive] [--dry-run]
```

1) Richiede slug (e, se interattivo, nome cliente).  
2) Crea struttura locale (`raw/`, `book/`, `config/`, `logs/`, `semantic/`).  
3) Copia template in `semantic/` (`cartelle_raw.yaml`, `semantic_mapping.yaml`) con blocco di contesto.  
4) Drive (opz.): se configurato, crea/aggiorna la struttura remota e carica `config.yaml`; aggiorna il config locale con gli ID.

> Con `--dry-run` lavora solo in locale, senza Drive.

---

## 2) Tagging semantico (HiTL)

```bash
py src/tag_onboarding.py --slug <id> [--source drive|local] [--local-path <dir>] [--proceed] [--non-interactive]
```

- Default: `--source=drive` — scarica i PDF dalla cartella RAW su Drive indicata in `config.yaml`.  
- Offline/locale: `--source=local` (opz. `--local-path <dir>`). Se `--local-path` è omesso, usa direttamente `output/timmy-kb-<slug>/raw/`.

Output Fase 1 — `semantic/tags_raw.csv` (path base-relative `raw/...` + colonne standard).  
Checkpoint HiTL — se confermato (o `--proceed`), Fase 2 genera `README_TAGGING.md` e `tags_reviewed.yaml` (stub).

> Validazione standalone: `py src/tag_onboarding.py --slug <id> --validate-only` produce `semantic/tags_review_validation.json`.

---

## 3) Semantic onboarding

```bash
Rem: vedi snippet Python sopra per invocazioni headless.

Nota per la UI: l'interfaccia Streamlit usa `semantic.api` come strato pubblico e stabile per tutta la logica semantica (niente dipendenza da helper interni).
```

- Conversione PDF -> Markdown in `book/`.  
- Arricchimento frontmatter dai tag canonici dal DB SQLite (`semantic/tags.db`).  
- Generazione `README.md` e `SUMMARY.md` (fallback idempotente).  
- Preview Docker (HonKit): in interattivo chiede se avviare/fermare; in CLI `--no-preview` la salta.

---

## 4) Onboarding Full (Push)

```bash
py src/onboarding_full.py --slug <id> [--non-interactive]
```

- Preflight `book/`: ammessi solo `.md`; i `.md.fp` sono ignorati.  
- Garantisce `README.md` e `SUMMARY.md`.  
- Push GitHub via `GITHUB_TOKEN` (chiede conferma in interattivo).

---

## Test (overview)

- I test sono deterministici, senza dipendenze di rete; le integrazioni esterne sono mockate/stub.  
- Prima di eseguirli, crea il dataset dummy:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  pytest -ra
  ```
- Dettagli, casi singoli e markers: vedi `docs/test_suite.md`.

---

## Log, sicurezza, exit codes

- Log centralizzati in `output/timmy-kb-<slug>/logs/`, con `run_id` e mascheramento automatico dei segreti (`LOG_REDACTION`).  
- Path-safety enforced (`ensure_within` SSoT) e scritture atomiche (`safe_write_text/bytes`).  
- Exit codes principali: 0 OK; 2 ConfigError; 30 PreviewError; 40 PushError.

---

## Note operative

- La preview richiede Docker; se assente viene saltata.  
- Pubblicazione su GitHub: vengono inclusi solo i `.md` di `book/`.  
- La sandbox/dataset dummy (`timmy-kb-dummy`) è usata nei test automatici per verificare coerenza e idempotenza della pipeline.  
- Per scenari air-gapped usa `tag_onboarding --source=local` e popola `raw/` manualmente.
