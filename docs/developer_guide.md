# Developer Guide
<!-- cSpell:ignore dataclass -->

> Questa guida descrive regole, flussi e convenzioni per contribuire a timmy-kb. È orientata a uno sviluppo rigoroso, idempotente e sicuro sul filesystem.

---

## Indice
- [Architettura in breve](#architettura-in-breve)
- [Fasi operative e facade `semantic.api`](#fasi-operative-e-facade-semanticapi)
- [Regole di sicurezza I/O e path-safety](#regole-di-sicurezza-io-e-path-safety)
- [Gestione errori, exit codes e osservabilità](#gestione-errori-exit-codes-e-osservabilità)
- [Conversione Markdown: policy ufficiale](#conversione-markdown-policy-ufficiale)
- [Qualità prima dei test (lint & format obbligatori)](#qualità-prima-dei-test-lint--format-obbligatori)
- [Variabili ambiente e segreti](#variabili-ambiente-e-segreti)
- [CI](#ci)
- [Enrichment & vocabolario: comportamento fail-fast](#enrichment--vocabolario-comportamento-fail-fast)
- [Vision Statement mapping](#vision-statement-mapping)
- [Indexer & KPI DB (inserimenti reali)](#indexer--kpi-db-inserimenti-reali)
- [Retriever API e calibrazione](#retriever-api-e-calibrazione)
- [UI: tab Finanza (I/O sicuro e cleanup)](#ui-tab-finanza-io-sicuro-e-cleanup)
- [Tooling: `gen_dummy_kb.py` e `retriever_calibrate.py`](#tooling-gen_dummy_kbpy-e-retriever_calibratepy)
- [Qualità del codice: lint, format, typing, test](#qualità-del-codice-lint-format-typing-test)
- [Linee guida di contributo](#linee-guida-di-contributo)

---

## Architettura in breve
- Orchestratori (CLI e UI) gestiscono l'esperienza utente e coordinano i moduli.
- `pipeline/*` fornisce utilità cross-cutting (path, file I/O, logging, context, validazioni) e rimane privo di accessi di rete; forte path-safety.
- `semantic/*` espone la facade `semantic.api` che coordina conversione PDF->MD, enrichment del frontmatter e indicizzazione.
- Storage locale: workspace per cliente in `output/timmy-kb-<slug>/{raw, book, semantic, config, logs}`.
- DB SQLite: Single Source of Truth (SSoT) per i tag in runtime (es. `semantic/tags.db`).

---

## Fasi operative e facade `semantic.api`
La facade `semantic.api` espone gli step principali:

1. `convert_markdown(ctx, logger, slug)`
   - Converte PDF in `raw/` in Markdown strutturato dentro `book/`.
   - Vedi policy nella sezione dedicata.

2. `write_summary_and_readme(ctx, logger, slug)`
   - Genera/aggiorna `SUMMARY.md` e `README.md` in `book/`.

3. `load_reviewed_vocab(base_dir, logger)`
   - Risolve i percorsi con `ensure_within_and_resolve` su `semantic/` e `tags.db`.
   - Se `tags.db` è assente: restituisce `{}` e registra un log informativo (enrichment disabilitato).
   - Lancia `ConfigError` solo per path non sicuri o DB illeggibile/corrotto (vedi sezione dedicata).

4. `enrich_frontmatter(ctx, logger, vocab, slug)`
   - Arricchisce il frontmatter dei Markdown con i metadati normalizzati.

5. `index_markdown_to_db(ctx, logger, slug, scope, embeddings_client, db_path)`
   - Estrae chunk testuali, calcola embedding, scrive su DB (idempotente) e ritorna KPI coerenti.

> Fase `build_markdown_book`: viene tracciata come singola fase che copre l'intero blocco `convert_markdown -> write_summary_and_readme -> load_reviewed_vocab -> enrich_frontmatter`. Il "successo è emesso solo a enrichment terminato; gli `artifacts` riflettono i soli contenuti effettivi (esclusi `README.md`/`SUMMARY.md`).

---

## Regole di sicurezza I/O e path-safety
- Guardie obbligatorie: usare sempre `ensure_within` / `ensure_within_and_resolve` prima di accedere a file/dir derivati da input esterni o configurazioni.
- Scritture atomiche: impiegare `safe_write_text`/`safe_write_bytes` per evitare file parziali e condizioni di gara.
- Append sicuro: usare `safe_append_text` quando serve aggiungere righe (es. audit JSONL); gestisce path-safety, lock file e fsync opzionale.
- No side-effects a import-time: i moduli non devono mutare `sys.path` né eseguire I/O quando importati.
- Idempotenza: tutti gli step devono poter essere ri-eseguiti senza effetti collaterali (cleanup dei temporanei garantito anche in errore).

---

## Gestione errori, exit codes e osservabilità
- Eccezioni tipizzate: usare le exception di progetto (`ConfigError`, `PipelineError`, `ConversionError`, …) e includere contesto.
- Contesto obbligatorio: tutti i `PipelineError` (e derivate) devono includere `slug` e `file_path` quando rilevanti.
- Orchestratori CLI: catturano `ConfigError`/`PipelineError` e mappano su exit codes deterministici tramite `exit_code_for`. Nessun traceback non gestito.
- `ClientContext.load(require_env=True)`: se le ENV obbligatorie mancano o sono vuote, solleva immediatamente `ConfigError` con messaggio chiaro (mai `KeyError`).
- Logging strutturato: usare `phase_scope(logger, stage=..., customer=...)` per `phase_started/phase_completed/phase_failed` e valorizzare `artifacts` con numeri reali.

---

## Controllo caratteri & encoding (UTF-8)

- `fix-control-chars`: hook pre-commit che ripulisce i file sostituendo i caratteri di controllo vietati e applicando la normalizzazione NFC.
- `forbid-control-chars`: hook di verifica che blocca il commit se restano caratteri proibiti o file non UTF-8.

Per forzare i controlli:

```bash
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files
python scripts/forbid_control_chars.py --fix <path>
```
## Qualità prima dei test (lint & format obbligatori)

Il codice deve essere conforme **prima del commit** a: `black` (format), `isort` (ordinamento import) e `flake8` (lint).
Standard: **line-length 120**, profilo `black` per `isort`, nessun segreto nei log.

Ogni contributor deve avere `pre-commit` attivo: i commit che non passano lint/format **non entrano** nel repo.
Regola pratica: *scrivi come se il linter stesse leggendo con te*. Se serve, formatta a mano, poi salva: l'editor applica `black` in automatico.

**Definition of Done (minimo) per ogni PR:**
- file formattati (`black`) e import ordinati (`isort`);
- `flake8` pulito (nessun F/E/W rilevante);
- messaggi di log privi di segreti;
- test esistenti non rotti.

### Setup qualità locale (obbligatorio)

1. Installa toolchain: `pip install -U pre-commit black isort flake8`.
2. Attiva hook: `pre-commit install`.
3. Editor (VS Code): abilita *format on save* con `black`, lint con `flake8`, `isort` profilo `black`, line-length 120.

**Prima di ogni commit**: esegui `pre-commit run --all-files` oppure salva i file (l'editor formatterà automaticamente).
Le PR vengono rifiutate se non superano lint/format. I test partono **dopo** il gate di qualità per far arrivare al testing solo codice già pulito.

> Nota: quando chiedi codice a tool/assistenti (es. Codex), specifica sempre: "rispetta line-length 120, black/isort/flake8; nessun segreto nei log".


---

## Variabili ambiente e segreti
- Mantieni chiavi distinte per servizio e ambiente (es. `OPENAI_API_KEY_CODEX` per la UI/RAG e `OPENAI_API_KEY_FOLDER` per i job batch).
- Popola i secret omonimi in GitHub (Settings -> Secrets and variables -> Actions) per ciascun ambiente CI/CD, evitando valori in chiaro nei log.
- In locale carica i segreti tramite `.env` e attiva la redazione (`LOG_REDACTION`) per prevenire tracce accidentali.

## CI
- Concurrency per ref/PR con `cancel-in-progress: true` per evitare job duplicati.
- Permissions minime (`contents: read`) se non servono scritture.
- Trigger `push`/`pull_request` limitati ai path rilevanti; schedule notturni invariati.

---

## Conversione Markdown: policy ufficiale
- Se `raw/` non esiste → `ConfigError` con `file_path`.
- Se `raw/` non contiene PDF:
  - Non chiamare il converter (evita segnaposto).
  - Se `book/` contiene già MD di contenuto → restituiscili.
  - Altrimenti → `ConfigError` (fail-fast, con `file_path=raw/`).
- Se ci sono PDF in `raw/` → invocare sempre il converter.
- Se in `raw/` i PDF trovati sono tutti non sicuri/symlink/fuori perimetro:
  - Non chiamare il converter.
  - Sollevare `ConfigError` con messaggio esplicito ("solo PDF non sicuri/fuori perimetro") e hint operativo a rimuovere i symlink o spostare i PDF reali dentro `raw/`.
- Gli `artifacts` conteggiano solo MD di contenuto (escludere `README.md`/`SUMMARY.md`).
- Categorie symlink: in presenza di categorie che sono link simbolici verso sottocartelle reali, i percorsi vengono risolti e verificati con path-safety per evitare loop e mismatch; l'emissione del markdown procede senza eccezioni usando la base risolta per il calcolo dei percorsi relativi.

---

## Enrichment & vocabolario: comportamento fail-fast
- SSoT runtime dei tag è sotto `semantic/` (tipicamente DB). L'assenza del DB è ok (nessun enrichment), restituisce `{}`.
- Errori di path o I/O/DB durante il load → `ConfigError` con `file_path` (fail-fast, niente fallback silenziosi).
- L'enrichment avviene nella fase estesa `build_markdown_book`; una failure blocca il "successo" della fase.

### Nota (Enrichment/Vocabolario - SQLite)
- Errori SQLite (apertura, query, cursor) durante la lettura del DB sono sempre rimappati a `ConfigError` con `file_path` al DB.

---

## Onboarding nuovo cliente (slug non esistente)
1. **Upload controllato**: la landing UI accetta solo `VisionStatement.pdf`. Il file viene salvato in `config/VisionStatement.pdf` nel workspace del cliente con guardie `ensure_within_and_resolve` e scrittura atomica.
2. **Genera da Vision (AI)**: dopo l'upload si attiva il pulsante **"Genera da Vision (AI)"**; il click avvia `semantic.vision_provision.provision_from_vision` e mostra la progress bar `[PDF ricevuto] -> [Snapshot] -> [YAML vision] -> [YAML cartelle]`.
3. **Anteprima YAML**: al termine la UI apre un expander con `semantic/semantic_mapping.yaml` e `semantic/cartelle_raw.yaml` per l'audit. Questo step crea `semantic/cartelle_raw.yaml` nel workspace e logga hash del PDF e modello usato.
4. **Approva e crea cartelle**: nessuna cartella `docs/` viene generata finche' l'utente non preme **"Approva e crea cartelle"**; il pulsante delega a `pipeline.provision_from_yaml.provision_directories_from_cartelle_raw(...)`, che legge `semantic/cartelle_raw.yaml` e crea la gerarchia in modo idempotente.
- **Idempotenza**: l'hash del PDF viene salvato in `semantic/.vision_hash`. Se l'utente rilancia con lo stesso file, la UI segnala che gli artefatti esistono gia' e permette la rigenerazione solo su richiesta esplicita (`force=True` o cambio modello).
- **Extra future**: la generazione di `tags_reviewed.yaml` resta fuori scope in questa fase e arrivera' in uno step dedicato alla revisione tassonomica.
## Vision Statement mapping
- `semantic.vision_ai.generate(ctx, logger, slug)` risolve i percorsi con `ensure_within_and_resolve`, estrae il testo dal PDF con PyMuPDF e salva sempre uno snapshot (`semantic/vision_statement.txt`) prima di inviare il prompt strutturato al modello `gpt-4.1-mini`.
- Lo YAML risultante (`semantic/semantic_mapping.yaml`) è scritto in modo atomico tramite `safe_write_text`; il JSON viene validato rispetto allo schema e i campi mancanti generano `ConfigError` espliciti.
- `src/tools/gen_vision_yaml.py` carica `.env` via `ensure_dotenv_loaded()`, inizializza il `ClientContext` e mappa gli errori (`ConfigError` -> exit code 2).
- I test `tests/test_vision_ai_module.py` coprono estrazione PDF, conversione JSON->YAML, logging snapshot e i casi di risposta troncata (`finish_reason="length"`).


## Indexer & KPI DB (inserimenti reali)
- `insert_chunks(...)` ritorna il numero effettivo di righe inserite (idempotenza: re-run → `0`).
- L'aggregato in `index_markdown_to_db(...)` usa la somma degli inserimenti reali per coerenti KPI/telemetria.
 - Inizializzazione schema DB: eseguita una sola volta per run e in modalità fail-fast; eventuali errori di inizializzazione vengono tipizzati come `ConfigError` con `file_path` puntato al DB effettivo (se `db_path` è `None` viene usato il percorso predefinito di `get_db_path()`).

---

## Retriever API e calibrazione
- `QueryParams` e' la dataclass SSoT per impostare la ricerca: richiede `project_slug`, `scope`, `query`, `k` e `candidate_limit`, con `db_path` opzionale per puntare a un DB specifico.
- `retrieve_candidates(params)` valida i parametri come la search reale e recupera i chunk grezzi tramite `fetch_candidates`, emettendo log strutturati `retriever.raw_candidates`.
- `search` e `search_with_config` restano l'interfaccia per la ricerca completa dopo la calibrazione del limite con config o budget.

Esempio d'uso minimo:

```python
from retriever import QueryParams, retrieve_candidates

params = QueryParams(
    db_path=None,
    project_slug="acme",
    scope="book",
    query="onboarding checklist",
    k=5,
    candidate_limit=2000,
)
raw_candidates = retrieve_candidates(params)
```

### Calibrazione retriever (`src/tools/retriever_calibrate.py`)
- Prerequisiti: workspace gia' popolato (es. `py src/tools/gen_dummy_kb.py --slug dummy`) e un file JSONL di query con righe `{"text": "...", "k": 5}`.
- Esecuzione tipica:

```powershell
py src/tools/retriever_calibrate.py --slug dummy --scope book --queries tests/data/retriever_queries.jsonl --limits 500:2500:500 --repetitions 3 --dump-top output/timmy-kb-dummy/logs/calibrazione.jsonl
```

- `--limits` accetta sia elenchi separati da virgola (`500,1000,2000`) sia range `start:stop:step`; `--repetitions` ripete la misura; `--dump-top` salva un JSONL con i documenti top-k usando `safe_write_text`.
- Log attesi: `retriever_calibrate.start`, piu' eventi `retriever.raw_candidates` dal wrapper, `retriever_calibrate.run` per ciascun sample e `retriever_calibrate.done` con media finale (se assenti run viene emesso `retriever_calibrate.no_runs`).
- Il tool non contatta servizi esterni: opera sul DB locale via `retrieve_candidates` e produce output deterministici da usare per aggiornare `candidate_limit` con `with_config_candidate_limit` o `with_config_or_budget`.

---

## UI: tab Finanza (I/O sicuro e cleanup)
- Scritture solo tramite `safe_write_bytes` con guardie `ensure_within`.
- Creazione del CSV temporaneo in `semantic/` con cleanup in `finally` (anche in caso d'errore).
- Niente fallback a `Path.write_bytes`.

---

## Tooling: `gen_dummy_kb.py` e `retriever_calibrate.py`
- `gen_dummy_kb.py`
  - Nessun side-effect a import-time; bootstrap delle dipendenze lazy in `_ensure_dependencies()`.
  - Supporta `--out <dir>` per generare un workspace esplicito; crea `raw/`, `book/`, `semantic/`, `config/`.
- `retriever_calibrate.py`
  - Costruisce `QueryParams` reali (slug, scope, query, limite) e usa il wrapper `retrieve_candidates`.
  - Logging strutturato: `retriever_calibrate.start/run/done` con `extra` sempre valorizzato per slug, scope, limite e tempi.
  - I dump opzionali dei doc top-k passano da `safe_write_text` dopo la guardia `ensure_within_and_resolve`.


---

## Qualità del codice: lint, format, typing, test
- Formatter/Lint: Black, isort, Ruff (config in `pyproject.toml`).
- Typing: mypy/pyright; preferire type hints espliciti, no `Any` se evitabile.
- Test: `pytest` con piramide unit → contract → smoke E2E; nessuna dipendenza di rete. Marcatori e `addopts` in `pytest.ini`.
- Pre-commit: hook per lint/format/type e sicurezza (es. gitleaks); i commit devono passare tutti gli hook.

Esecuzione locale suggerita:
```bash
make install
make fmt && make lint && make type
make test
```

---

## Linee guida di contributo
1. Modifiche minime e reversibili: evitare refactor ampi senza necessità.
2. Niente nuove dipendenze senza forte motivazione e consenso.
3. Aggiornare la documentazione e il CHANGELOG per ogni modifica rilevante.
4. Definition of Done: lint/format/type/test verdi; nessuna regressione osservata nei workflow E2E; log strutturati coerenti.

> Per dubbi o proposte di evoluzione, apri una PR con descrizione completa (contesto, impatti, rischi, rollback) e riferimenti ai test/telemetria.
