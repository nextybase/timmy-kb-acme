# Timmy KB - README (v1.9.5)

[![Bench Embeddings Normalization](https://github.com/nextybase/timmy-kb-acme/actions/workflows/bench.yml/badge.svg)](https://github.com/nextybase/timmy-kb-acme/actions/workflows/bench.yml) [![Docs Spellcheck](https://github.com/nextybase/timmy-kb-acme/actions/workflows/docs-spellcheck.yml/badge.svg)](https://github.com/nextybase/timmy-kb-acme/actions/workflows/docs-spellcheck.yml)

Pipeline per la generazione di una Knowledge Base Markdown AI-ready a partire da PDF cliente, con arricchimento semantico, anteprima HonKit (Docker) e push opzionale su GitHub.

> See also: [Architecture](docs/architecture.md).

## Comportamento rilevante (Indexing/Retriever)
- Indicizzazione parziale: se `len(embeddings) != len(contents)` l'indice usa il minimo comune; nessun cambio di schema o API.
- Telemetria run vuoti: rami "no files"/"no contents" entrano in `phase_scope` con `artifacts=0` e chiudono con `semantic.index.done`.
- Conversione DRY: se passi `safe_pdfs` già validati/risolti in `raw/`, la conversione usa solo quell'elenco (niente discovery) e pulisce `.md` orfani in modo idempotente.
- Retriever: short‑circuit per embedding già `list[float]` (ranking invariato); log unico `retriever.metrics` con tempi `{total, embed, fetch, score_sort}` e `coerce {short, normalized, skipped}`.

Esempi log compatti
```
semantic.index.mismatched_embeddings  embeddings=1 contents=2
semantic.index.embedding_pruned dropped=1
semantic.index.skips skipped_io=0 skipped_no_text=0 vectors_empty=1
```

Per dettagli vedi anche: `docs/developer_guide.md` (Indexer & Retriever) e la nuova sezione Troubleshooting in `docs/index.md`.

## Troubleshooting

### "Percorso RAW non è una directory: <path>"
- Causa: il percorso `raw/` non esiste o punta a un file; oppure path non sicuro.
- Azione: crea `output/timmy-kb-<slug>/raw/` (directory, non file), verifica permessi e path‑safety (`ensure_within*/resolve`).

### Indicizzazione senza contenuti ("no contents")
- Sintomi: `phase_scope` con `artifact_count=0`, log `semantic.index.no_valid_contents` e (se presenti) unico `semantic.index.skips` con `{skipped_io, skipped_no_text, vectors_empty}`.
- Azione: verifica i `.md` in `book/` (non vuoti), controlla warning `semantic.index.read_failed` ed esito del client embeddings (no vettori vuoti).

## Novità v1.9.5

- Vision Statement pipeline: `src/semantic/vision_ai.py` estrae il testo dal PDF, lo salva in `semantic/vision_statement.txt` e genera il mapping JSON/YAML via `gpt-4.1-mini`.
- CLI `py src/tools/gen_vision_yaml.py --slug <slug>` carica `.env` automaticamente, valida i percorsi e produce `semantic/semantic_mapping.yaml`.
- Suite: `tests/test_vision_ai_module.py` copre l'estrazione dal PDF, la conversione JSON->YAML e gli scenari di errore dell'assistant.

---

## Novità v2.0.0

- Guardie esplicite per Google Drive negli orchestratori (pre/tag_onboarding) e nella UI (drive_runner), con errori chiari e hint `pip install .[drive]` se mancano gli extra.
- UI: caricamento `.env` idempotente per `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`.
- Installazione nativa via `pyproject.toml`:
  - extra `drive`: `pip install .[drive]`.
  - dipendenze base per `pip install .` (SSoT dei pin in `requirements.txt`).
- CI: workflow `import-smoke` non-gating su PR; `bench.yml` opzionale.
- Test: aggiunti `tests/test_tag_onboarding_drive_guard_main.py` e `tests/test_ui_drive_services_guards.py`.

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
   Verifica che in `book/` ci siano solo `.md` (i `.md.fp` vengono ignorati), genera/valida `README.md` e `SUMMARY.md` e pubblica su GitHub.

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
- `OPENAI_API_KEY_CODEX`: credenziale per la UI Timmy KB Coder e i servizi RAG basati su Codex.
  - Fallback Coder: se `OPENAI_API_KEY` non è impostata, la UI Coder usa `OPENAI_API_KEY_CODEX` come chiave embeddings
    e registra `embeddings.api_key.source=codex_fallback` nei log.
  - Se entrambe sono presenti, viene usata `OPENAI_API_KEY` (nessun fallback/log).
- `OPENAI_API_KEY_FOLDER`: credenziale separata per i job di ingest folder e gli script batch basati su OpenAI
- `YAML_STRUCTURE_FILE`: override opzionale del file YAML per il pre-onboarding (default `config/cartelle_raw.yaml`)
- `LOG_REDACTION`: `auto` (default), `on`, `off`
- `ENV`, `CI`: Modalità operative

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

> Lo slug deve rispettare le regole in `config/config.yaml`. In interattivo, se non valido, viene richiesto di correggerlo.

---

## Vision Statement -> YAML

> Genera il mapping semantico partendo dal Vision Statement del cliente.

```bash
py src/tools/gen_vision_yaml.py --slug <slug>
```

- Input: `VisionStatement.pdf` cercato in `config/`, `raw/` o nel `config/` globale del repo.
- Output: `semantic/semantic_mapping.yaml` (mapping strutturato) e `semantic/vision_statement.txt` (snapshot testuale).
- Richiede `OPENAI_API_KEY_FOLDER` o `OPENAI_API_KEY` nel `.env`; lo script richiama `ensure_dotenv_loaded()` automaticamente.
- Il modello `gpt-4.1-mini` produce un JSON conforme allo schema e viene serializzato in YAML; risposte vuote o troncate sollevano `ConfigError`.

---

## Modalità d'uso

> Doppio approccio: puoi lavorare da terminale usando gli orchestratori in sequenza oppure tramite interfaccia (Streamlit).

### Interattiva (prompt guidati)
```bash
py src/pre_onboarding.py
py src/tag_onboarding.py
py - <<PY
from semantic.api import convert_markdown, enrich_frontmatter, write_summary_and_readme
from pipeline.context import ClientContext
import logging
slug = 'acme'
ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
log = logging.getLogger('semantic.manual')
convert_markdown(ctx, log, slug=slug)
base = ctx.base_dir
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
py src/semantic_onboarding.py --slug acme --non-interactive                  # wrapper fase Semantica
```

Nota
- `convert_markdown` fallisce se, dopo la conversione, esistono solo `README.md`/`SUMMARY.md` (nessun contenuto): assicurati che `raw/` contenga PDF.
- Se la conversione segnala "solo PDF non sicuri/fuori perimetro": in `raw/` ci sono solo symlink o file fuori dal perimetro di sicurezza. Rimuovi i symlink o sposta i PDF reali dentro `raw/` e ripeti.
- L'indicizzazione esclude `README.md` e `SUMMARY.md` e scarta eventuali embedding vuoti per singolo file (log: "Embedding vuoti scartati").
- Se in `raw/` hai categorie che sono symlink verso sottocartelle reali, la conversione gestisce i link in modo
  robusto risolvendo i percorsi in sicurezza (path-safety) ed evitando loop/mismatch; i markdown di categoria vengono
  generati senza errori.

### Interfaccia (Streamlit)
L'alternativa agli orchestratori via terminale è l'interfaccia.

Avvio:
```bash
streamlit run onboarding_ui.py
```
Guida completa: `docs/guida_ui.md`.

---

## Sezione UI: Ricerca (retriever)

Nella sidebar è presente un box apri/chiudi "Ricerca (retriever)" che consente di configurare:
- `candidate_limit`: massimo numero di candidati caricati dal DB prima del ranking (min 500, max 20000). Valori più alti aumentano la latenza.
- `budget di latenza (ms)`: indicazione del budget desiderato (0 = disabilitato). Usato solo se attivi l’auto.
- `Auto per budget`: se attivo, il sistema sceglie automaticamente un `candidate_limit` in base al budget (euristica interna; calibrabile).

Le impostazioni sono salvate nel `config.yaml` del cliente sotto la chiave `retriever`:
```yaml
retriever:
  candidate_limit: 4000
  latency_budget_ms: 300
  auto_by_budget: false
```

Uso a codice (API): passa dalle utilità del retriever per applicare i valori da config con la precedenza giusta:
```python
from src.retriever import QueryParams, with_config_or_budget, search
from pipeline.config_utils import get_client_config

params = QueryParams(db_path=..., project_slug=..., scope=..., query="...", k=8)
cfg = get_client_config(ctx)  # dal tuo ClientContext
params = with_config_or_budget(params, cfg)
results = search(params, embeddings_client)
```

Note: il retriever logga tempi di fase (embed/fetch/score+sort/total) per facilitare la calibrazione.

---

## Dipendenze Drive

Le funzionalità Drive richiedono `google-api-python-client`. Se la dipendenza non è installata:
- l’import del modulo `pipeline.drive_utils` fallisce con `ImportError` esplicito;
- la UI mostra un banner nella sezione Drive con le istruzioni per l’installazione.

Installazione:
```bash
pip install google-api-python-client
```

Nota (consigliata): per uno setup completo usare gli extra del progetto:
```bash
pip install .[drive]
# sviluppo
pip install -e ".[drive]"
```
Se le dipendenze Drive non sono installate e scegli la sorgente Drive, CLI/UI mostrano messaggi chiari con le istruzioni d’installazione; i flussi offline (source=local, --dry-run) restano funzionanti.

---

## 1) Pre-onboarding

```bash
py src/pre_onboarding.py [--slug <id>] [--name <nome>] [--non-interactive] [--dry-run]
```

1) Richiede slug (e, se interattivo, nome cliente).
2) Crea struttura locale (`raw/`, `book/`, `config/`, `logs/`, `semantic/`).
3) Copia template in `semantic/` (`cartelle_raw.yaml`, `tags_reviewed.yaml` + duplicato `semantic_mapping.yaml` per compatibilita UI) con blocco di contesto.
4) Drive (opz.): se configurato, crea/aggiorna la struttura remota e carica `config.yaml`; aggiorna il config locale con gli ID.

> Con `--dry-run` lavora solo in locale, senza Drive.

---

## QA locale (linters, type-check, test)

- Installa i hook di pre-commit (pre-commit e pre-push):

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

- Hook pre-commit: esegue un controllo "safe" (isort/black/ruff/mypy se presenti). Degrada con skip se gli strumenti non sono installati.

- Hook pre-push: esegue `qa-safe --with-tests` (pytest se presente) e un mypy mirato (vedi `.pre-commit-config.yaml`).

- Esecuzione manuale dei check "safe":

```bash
make qa-safe     # isort/black/ruff/mypy (se presenti)
make ci-safe     # qa-safe + pytest (se presente)
make test        # esegue pytest con l'interprete attivo del venv
make test-vscode # usa ./venv se non hai attivato il venv
```

- Nota venv/PATH: se i binari (ruff/black/mypy) non sono nel PATH della shell, esegui i check tramite l'interprete del venv.
  - Windows: `venv\Scripts\python.exe -m ruff check src tests && venv\Scripts\python.exe -m black --check src tests && venv\Scripts\python.exe -m mypy src`
  - Linux/macOS: `venv/bin/python -m ruff check src tests && venv/bin/python -m black --check src tests && venv/bin/python -m mypy src`
  - Per usare i comandi globali, attiva prima il venv: Windows `venv\Scripts\activate`, Linux/macOS `source venv/bin/activate`.

### Setup cspell (VS Code)

- Installa le dev dipendenze Node per i dizionari: `npm ci` (o `npm install`).
- Se l'estensione VS Code mostra warning su `@cspell/dict-it-it`, ricarica la finestra: "Developer: Reload Window".
- L'hook pre-commit usa `npx -p @cspell/dict-it-it ...` e funziona anche senza `node_modules`, ma l'estensione VS Code richiede comunque `node_modules/` locali.
---

## Benchmark normalizzazione embeddings

È disponibile un micro-benchmark per validare la normalizzazione degli output degli embedding sia nel retriever sia nell’indicizzazione semantica.

- Esecuzione rapida: `make bench`
- Alternativa diretta: `py -m scripts.bench_embeddings_normalization`

Il benchmark misura (best-of-5) diversi formati di output di `embed_texts`:
- `numpy.ndarray` 2D
- `list[np.ndarray]`
- vettore singolo come `deque` o generatore

Nota: le misure sono indicative e servono come regression check locale.
---

## 2) Tagging semantico (HiTL)

```bash
py src/tag_onboarding.py --slug <id> [--source drive|local] [--local-path <dir>] [--proceed] [--non-interactive]
```

- Default: `--source=drive` — scarica i PDF dalla cartella RAW su Drive indicata in `config.yaml`.
- Offline/locale: `--source=local` (opz. `--local-path <dir>`). Se `--local-path` è omesso, usa direttamente `output/timmy-kb-<slug>/raw/`.

Output Fase 1 — `semantic/tags_raw.csv` (path base-relative `raw/...` + colonne standard).
Checkpoint HiTL — se confermato (o --proceed), Fase 2 genera `README_TAGGING.md` e `tags_reviewed.yaml` (stub).

> Validazione standalone: py src/tag_onboarding.py --slug <id> --validate-only produce `semantic/tags_review_validation.json`.

Nota sicurezza (CSV): l'emissione di `tags_raw.csv` usa un writer centralizzato con path-safety forte
(ensure_within_and_resolve + ensure_within) e scrittura atomica. Il writer richiede un base_dir
esplicito come perimetro della sandbox cliente; la facade `semantic.api.build_tags_csv(...)` incapsula
questo contratto e passa base_dir dal contesto.

Guardie Drive: in CLI (`tag_onboarding`) viene sollevato ConfigError se scegli `--source=drive` senza extra installati; in UI i servizi Drive sollevano RuntimeError con istruzioni di installazione.

---

## 3) Semantic onboarding

```bash
Rem: vedi snippet Python sopra per invocazioni headless.

Nota per la UI: l'interfaccia Streamlit usa `semantic.api` come strato pubblico e stabile per tutta la logica semantica (niente dipendenza da helper interni).

Riferimento rapido alle nuove API additive (v1): vedi la sezione "API Semantiche Additive (v1)" in `.codex/WORKFLOWS.md`.
```

- Conversione PDF -> Markdown in `book/`.
- Arricchimento frontmatter dai tag canonici dal DB SQLite (`semantic/tags.db`).
- Generazione `README.md` e `SUMMARY.md` (fallback idempotente).
- Preview Docker (HonKit): in interattivo chiede se avviare/fermare; in CLI `--no-preview` la salta.

Error handling: ConfigError se `RAW` o i PDF mancano; ConversionError se la conversione non produce Markdown o se la generazione di README/SUMMARY fallisce.

---

## 4) Onboarding Full (Push)

```bash
py src/onboarding_full.py --slug <id> [--non-interactive]
```

- Preflight `book/`: ammessi solo `.md`; i `.md.fp` sono ignorati.
- Garantisce `README.md` e `SUMMARY.md`.
- Push GitHub via `GITHUB_TOKEN` (chiede conferma in interattivo).

Requisito: variabile `GITHUB_TOKEN` presente. Errori: ConfigError se il token manca; PushError su fallimenti di push.

---

## Test (overview)

- I test sono deterministici, senza dipendenze di rete; le integrazioni esterne sono mockate/stub.
- Prima di eseguirli, crea il dataset dummy:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  pytest -ra
  ```
- Dettagli, casi singoli e markers: vedi `docs/test_suite.md`.

### Type checking rapido
- Mypy: `make type`
- Pyright: `make type-pyright` (richiede `pyright` nel PATH oppure `npx`)

---

## Log, sicurezza, exit codes

- Log centralizzati in `output/timmy-kb-<slug>/logs/`, con `run_id` e mascheramento automatico dei segreti (`LOG_REDACTION`).
- Path-safety enforced (`ensure_within` SSoT) e scritture atomiche (`safe_write_text/bytes`).
- Exit codes principali: 0 OK; 2 ConfigError; 30 PreviewError; 40 PushError.

---

## Ingest/CSV — Best Practice

- Usa esclusivamente le API pubbliche in semantic.api:
 - `copy_local_pdfs_to_raw(src_dir, raw_dir, logger)` per copiare PDF locali in `raw/`.
 - `build_tags_csv(context, logger, *, slug)` per generare `semantic/tags_raw.csv` (+ README tagging).
- Evita helper locali e import diretti da `semantic.tags_extractor` fuori da `src/semantic/`.
- Un hook pre-commit (no-dup-ingest-csv) previene regressioni su duplicazioni/usi non consentiti.

- Su Windows, se il binario `pre-commit` non è nel PATH del venv, usa Python launcher:
  - `py -3.11 -m pre_commit install --hook-type pre-commit --hook-type pre-push`
  - `py -3.11 -m pre_commit run -a`

---

## Note operative

- La preview richiede Docker; se assente viene saltata.
- Pubblicazione su GitHub: vengono inclusi solo i `.md` di `book/`.
- La sandbox/dataset dummy (`timmy-kb-dummy`) è usata nei test automatici per verificare coerenza e idempotenza della pipeline.
- Per scenari air-gapped usa `tag_onboarding --source=local` e popola `raw/` manualmente.
