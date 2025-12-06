# Runbook Codex - Timmy KB (v1.0 Beta)

> Questo runbook e' la guida **operativa** per lavorare in sicurezza ed efficacia sul repository **Timmy KB** con approccio *Agent-first* e supervisione **HiTL**. E' la fonte principale per i flussi quotidiani; i dettagli di design vivono negli altri documenti tecnici indicati nei rimandi.

- **Audience:** developer, tech writer, QA, maintainers, agent "Codex" (repo-aware).
- **Scope:** operazioni locali, UI/CLI, integrazioni OpenAI/Drive/GitHub, sicurezza I/O e path-safety, qualita', rollback e risoluzione problemi.
- **Rimandi canonici:** [Developer Guide](developer_guide.md), [Coding Rules](coding_rule.md), [Architecture Overview](architecture.md), [AGENTS Index](AGENTS_INDEX.md), [.codex/WORKFLOWS](../.codex/WORKFLOWS.md), [.codex/CHECKLISTS](../.codex/CHECKLISTS.md), [User Guide](user_guide.md).

> **Nota:** questo runbook si integra con il documento
> **[`docs/codex_integrazione.md`](codex_integrazione.md)**
> che definisce il *Workflow Codex + Repo-Aware (v2)*, l’uso dei tre SSoT (AGENTS_INDEX, AGENTS di area, `~/.codex/AGENTS.md`),
> e l’entrypoint operativo *Onboarding Task Codex*.
> Il runbook resta la guida pratica per l’esecuzione dei flussi, mentre `codex_integrazione.md` definisce il modello mentale e metodologico.

---

## 1) Prerequisiti & setup rapido

**Tooling minimo**
- Python **>= 3.11**, `pip`, `pip-tools`; (opz.) **Docker** per preview HonKit.
  Vedi anche README -> *Prerequisiti rapidi*.
- Credenziali: `OPENAI_API_KEY`, `GITHUB_TOKEN`; per Drive: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`. <!-- pragma: allowlist secret -->
- Pre-commit: `pre-commit install --hook-type pre-commit --hook-type pre-push`.
- Preflight UI: verifica che i moduli pipeline siano importabili dalla stessa root della UI; in caso di mismatch attiva il venv corretto ed esegui `pip install -e .` dal root del repo.

**Ambiente**
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt   # se serve Drive
make qa-safe
pytest -q
```
Riferimenti: [README](../README.md), [Developer Guide -> Dipendenze & QA](developer_guide.md).

### Workflow Codex (operativo) – Allineamento rapido
- Prima di eseguire attività di sviluppo/refactor, l’agente Codex deve caricare i tre SSoT:
  `docs/AGENTS_INDEX.md` + `AGENTS.md` dell’area + `~/.codex/AGENTS.md`.
- L’entrypoint suggerito è **Onboarding Task Codex** definito in `.codex/PROMPTS.md`.
- Ogni intervento deve produrre una *micro-PR* idempotente, con QA documentata nel messaggio finale.
- I flussi e le azioni Codex devono essere coerenti con le policy del runbook e la Matrice AGENTS.

### Integrazione con `.codex/PROMPTS.md` (obbligatoria)
- I prompt in `.codex/PROMPTS.md` costituiscono la **API operativa** ufficiale per l’agente Codex.
- Prima di ogni task agent-based, Codex esegue il blocco “Task di avvio” definito in `.codex/PROMPTS.md`: lettura di `docs/AGENTS_INDEX.md`, dell’`AGENTS.md` dell’area, di `.codex/AGENTS.md` e di questo stesso runbook.
- Il prompt **Onboarding Task Codex** è l’entrypoint vincolante per i task di sviluppo/refactor:
  - definisce il piano di lavoro prima delle modifiche,
  - impone micro-PR non-breaking,
  - applica la checklist QA (path-safety, scritture atomiche, logging strutturato),
  - richiede l’aggiornamento della documentazione e della matrice AGENTS quando toccate.
- In questo modo tutti i flussi descritti nel runbook restano allineati alle regole operative codificate in `.codex/PROMPTS.md`.

---

## 2) Configurazione: `.env` (segreti) vs `config/config.yaml` (config)

- **SSoT:** segreti **fuori** repo in `.env`; configurazione applicativa **versionata** in `config/config.yaml`.
  Esempi e policy: [docs/configurazione.md](configurazione.md).

**Esempio corretto (`config/config.yaml`, vedi anche `config/config.example.yaml`):**
```yaml
meta:
  client_name: "Cliente Demo"
ui:
  skip_preflight: true
  allow_local_only: true
  admin_local_mode: false
ai:
  openai:
    timeout: 120
    max_retries: 2
    http2_enabled: false
  vision:
    model: gpt-4o-mini-2024-07-18
    engine: assistants
    assistant_id_env: OBNEXT_ASSISTANT_ID
    snapshot_retention_days: 30
pipeline:
  retriever:
    auto_by_budget: false
    throttle:
      candidate_limit: 3000
      latency_budget_ms: 300
      parallelism: 1
      sleep_ms_between_calls: 0
  raw_cache:
    ttl_seconds: 300
    max_entries: 8
```
**Regole operative**
- Le chiamate **dirette** leggono `ai.vision.model` (UI/CLI).
- Il flusso **Assistant** usa l'ID letto da `ai.vision.assistant_id_env` (ENV).
- La UI legge il modello tramite `get_vision_model()` (SSoT).
- Il retriever applica i limiti da `pipeline.retriever.throttle.*` (candidate_limit, latency, parallelism).
- Il retriever logga `retriever.query.embed_failed` e short-circuita a `[]` su errori embedding; se `latency_budget_ms` e gia esaurito interrompe prima di embedding/fetch.
- I flag `ui.allow_local_only` e `ui.admin_local_mode` governano gating e accesso al pannello Admin.

Riferimenti: [Developer Guide -> Configurazione](developer_guide.md), [Configuration](configurazione.md).

---

## 3) Sicurezza & path-safety (vincolante)

- **Path-safety:** qualsiasi I/O passa da `pipeline.path_utils.ensure_within*`.
- **Scritture atomiche:** `pipeline.file_utils.safe_write_text/bytes` (temp + replace).
- **Logging strutturato:** `pipeline.logging_utils.get_structured_logger` con **redazione** segreti quando `LOG_REDACTION` e' attivo.
  - Rotazione file configurabile via ENV `TIMMY_LOG_MAX_BYTES` / `TIMMY_LOG_BACKUP_COUNT` (default 1 MiB, 3 backup).
  - I log cliente vivono in `output/timmy-kb-<slug>/logs/`; i log UI globali in `.timmykb/logs/`. Entrambi sono consultabili dalla pagina Streamlit **Log dashboard**.
  - L'entrypoint UI crea automaticamente `.timmykb/logs/ui.log` con handler condiviso; Promtail estrae `run_id` e (se OTEL attivo) `trace_id`/`span_id` dai log per la correlazione Grafana.
  - `TIMMY_LOG_PROPAGATE` forza la propagazione verso handler parent; senza override rimane `False` per evitare duplicazioni console.
  - Export tracing (OTLP/HTTP) con `TIMMY_OTEL_ENDPOINT` + `TIMMY_SERVICE_NAME` + `TIMMY_ENV`: `phase_scope` aggiunge `trace_id`/`span_id` ai log e crea span nidificati.
- **Hash & masking:** le funzioni `hash_identifier` / `sha256_path` producono digest a 32 caratteri e accettano `TIMMY_HASH_SALT` per rafforzare l'entropia dei log; `mask_id_map` resta la via raccomandata per extra sensibili.
- **Cache RAW PDF:** `iter_safe_pdfs` usa cache LRU con TTL/cap configurabili in `config/config.yaml` (`pipeline.raw_cache.ttl_seconds`/`max_entries`); le scritture PDF con `safe_write_*` invalidano e pre-riscaldano la cache.
- **Cache frontmatter Markdown (refresh):** dopo le write il contenuto e riallineato nella cache LRU (256 entry); i workflow semantici orchestrati da `semantic.api` svuotano sempre la cache a fine run per evitare riuso involontario di stato nella stessa process.
- **Cache frontmatter Markdown:** `_FRONTMATTER_CACHE` e LRU bounded (256 entry) con promotion; nei run lunghi (UI/CLI) puoi chiamare `clear_frontmatter_cache()` per liberare memoria o isolare batch non semantici.
- **UI import-safe:** nessun side-effect a import-time; wrapper mantengono la **parita' di firma** col backend.
- **Download Drive safe-by-default:** la modale UI scarica solo i PDF mancanti; per sovrascrivere attiva il toggle *"Sovrascrivi i file locali in conflitto"* (abilitato solo se il piano rileva conflitti) oppure rimuovi/rinomina i file a mano.
- **Preview stub log dir:** `PREVIEW_LOG_DIR` puo' indicare anche un path assoluto; se la directory non e' raggiungibile la UI avvisa e ripiega su `logs/preview` sotto il repository.
- **Ingest telemetry:** `ingest_path` / `ingest_folder` emettono `phase_scope` (`ingest.embed`, `ingest.persist`, `ingest.process_file`, `ingest.summary`) con `artifact_count` impostato ai chunk/embedding salvati; usa questi eventi per dashboard e alerting sul flusso di ingestion.
- **Ingest streaming:** `ingest_folder` processa i glob in streaming (`iglob`) e accetta i limiti opzionali `max_files` / `batch_size` per throttling su corpus molto grandi; sfruttali negli script di migrazione per evitare OOM.

**Snippet tipici**
```python
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger

log = get_structured_logger("ui.manage.tags", context={"slug": "acme"})
yaml_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml")
safe_write_text(yaml_path, yaml_content, encoding="utf-8", atomic=True)
log.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
```

Riferimenti: [Developer Guide -> Logging](developer_guide.md), [Coding Rules -> I/O sicuro & Path-safety](coding_rule.md).

---

### Stack osservabilita (Loki/Grafana/Promtail)

- Config pronta in `observability/docker-compose.yaml` + `observability/promtail-config.yaml`.
- Promtail monta `../output/` e `../.timmykb/logs/` (relative alla cartella `observability/`), legge `*.log`, estrae le label `slug`, `run_id`, `event` dalle tuple `key=value` dei log Timmy.
- Avvio locale:
  ```bash
  cd observability
  docker compose up -d
  ```
  Grafana: `http://localhost:3000` (`admin`/`admin` da cambiare via `GF_SECURITY_ADMIN_PASSWORD`), Loki: `http://localhost:3100`.
- Spegnimento: `docker compose down`. Per ambienti Windows ricordarsi di condividere i percorsi `output` e `.timmykb` con Docker Desktop.
- Il docker compose ora include anche `tempo` (porta 3200/4317) e `otel-collector` (porta 4318) per esporre il tracing; il collector riceve OTLP HTTP dal TIMMY_OTEL_ENDPOINT del host e invia OTLP gRPC a Tempo, che a sua volta viene collegato da Grafana tramite il datasource `Tempo`.
- Le stesse operazioni possono essere eseguite anche dalla UI *Log dashboard* (Start/Stop Stack) o dallo script `tools/observability_stack.py` che chiama `docker compose` con gli stessi file `.env`/compose della UI. Lancia `python tools/observability_stack.py start|stop` e, se hai bisogno di percorsi alternativi, usa `--env-file` e `--compose-file` (o imposta `TIMMY_OBSERVABILITY_ENV_FILE` / `TIMMY_OBSERVABILITY_COMPOSE_FILE`).

---

### Script legacy

- Gli script non piu supportati sono stati spostati in `tools/archive/` ed esclusi dai flussi standard.
- Milestone di stabilizzazione: vedi `docs/milestones/archive_cleanup.md`; al termine la cartella verra rimossa.

---

## 4) Flussi operativi (UI/CLI) - panoramica

> Obiettivo: trasformare PDF -> **KB Markdown AI-ready** con frontmatter coerente, README/SUMMARY, preview HonKit e push opzionale su GitHub.

**End-to-end (workflow standard)**
1. **pre_onboarding** -> crea workspace `output/timmy-kb-<slug>/...`, opz. provisioning Drive + upload config.
2. **tag_onboarding** -> `semantic/tags_raw.csv` + **checkpoint HiTL** -> `tags_reviewed.yaml` (authoring).
3. **semantic_onboarding** (via `semantic.api`) -> **PDF->Markdown** (`book/`), **frontmatter enrichment** (SSoT `semantic/tags.db`), **README/SUMMARY** e preview **Docker**; le fasi condividono l'orchestratore `_run_build_workflow` e loggano `semantic.book.frontmatter`.
4. **onboarding_full** -> preflight (solo `.md` in `book/`) -> **push GitHub**.

**Gating UX (UI)**
- La tab **Semantica** si abilita **solo** se `raw/` locale e' presente.
- Preview Docker: validazione porta e `container_name` sicuro.
- Telemetria semantica: `semantic.book.frontmatter` logga il numero di file arricchiti (UI/CLI).

Riferimenti: [.codex/WORKFLOWS](../.codex/WORKFLOWS.md), [User Guide](user_guide.md), [Architecture](architecture.md).

---

## 5) Scenari Codex (repository-aware)

> Lo scenario **Agent** e' predefinito; **Full Access** e' eccezione con branch dedicati. Chat "solo testo" e' possibile ma **non** effettua write/push.

### 5.0 Principi operativi comuni (v2)
- Lo scenario **Agent** è predefinito; usa path-safety, scritture atomiche e aggiornamento docs/test.
- Tutte le attività devono rispettare:
  - workflow Codex v2 (`codex_integrazione.md`)
  - perimetro AGENTS (AGENTS_INDEX + AGENTS locali)
  - micro-PR + QA esplicita.
- I prompt Codex vanno selezionati da `.codex/PROMPTS.md`; l’entrypoint raccomandato è **Onboarding Task Codex**.
- Il modello a tre attori (Sviluppatore ↔ Codex ↔ Senior Reviewer) guida la collaborazione per i task sensibili.

### 5.1 Scenario *Chat*
- Solo reasoning/risposte; nessun I/O. Utile per grooming, draft e check veloci.

### 5.2 Scenario *Agent* (consigliato)
- L'agente opera **on-rails**: path-safety, scritture atomiche, micro-PR, aggiornamento docs/test nello stesso change set.
- **Matrice di policy**: vedi [AGENTS Index](AGENTS_INDEX.md). Gli `AGENTS.md` locali definiscono **solo** override di ambito.

### 5.3 Scenario *Full Access* (eccezione)
- Consentito **solo** su branch di lavoro dedicati per task espliciti (migrazioni/operazioni massive).
- Deve usare gli helper GitHub interni: `pipeline.github_push_flow._prepare_repo/_stage_changes/_push_with_retry/_force_push_with_lease`, oltre ai flag gestiti in `pipeline.github_env_flags`.
- Per la pipeline semantic, delega sempre a `semantic.convert_service`, `semantic.frontmatter_service` e `semantic.embedding_service`; `semantic.api` resta un facade che re-esporta le funzioni pubbliche.
- Le fasi NLP (doc_terms/cluster) vanno orchestrate tramite `semantic.nlp_runner.run_doc_terms_pipeline` e lo shim `tag_onboarding.run_nlp_to_db`, che gestiscono telemetria, retry e accessi DB in modo sicuro.
- Ogni operazione e' tracciata a log; PR o commit devono essere **atomici** e verificabili.

### 5.4 Multi-agent alignment
- Allinea flag e configurazioni (`TIMMY_NO_GITHUB`, `GIT_FORCE_ALLOWED_BRANCHES`, `TAGS_MODE`, throttle NLP) su UI, CLI e agent: aggiorna `.env.sample` e documentazione quando cambiano.
- Verifica che gli adapter opzionali (`ui.services.tags_adapter`, servizi Drive) siano disponibili oppure che la UI mostri fallback (modalita' stub) e messaggi di help coerenti.
- Monitora la telemetria `phase_scope`: tutte le pipeline devono emettere `prepare_repo`, `stage_changes`, `push_with_retry`/`force_push` per semplificare il triage cross-team.
- Sincronizza le cache condivise (`clients_store`, `safe_pdf_cache`) invalidandole dopo le write atomiche e tracciando nei log `reset_gating_cache`.

Riferimenti: [AGENTS Index](AGENTS_INDEX.md), [.codex/AGENTS](../.codex/AGENTS.md).

---

## 6) Qualita', test & CI

- **Piramide test:** unit -> contract/middle -> smoke E2E (dataset **dummy**, zero rete).
- **Hook pre-commit:** format/lint (`isort`, `black`, `ruff --fix`), type-check (`mypy`/`pyright`), spell-check cSpell su `docs/`, guard rail `forbid-*`.
- **CI locale rapida:** `make qa-safe` -> `make ci-safe` -> `pytest -q`.

**Casi minimi obbligatori**
- Slug invalidi scartati/normalizzati.
- Traversal via symlink in `raw/` negato.
- Parita' di firma wrapper UI <-> backend e pass-through parametri.
- Invarianti `book/`: `README.md`/`SUMMARY.md` sempre presenti; `.md.fp` **esclusi** da push.

Riferimenti: [Developer Guide -> Test](developer_guide.md), [Coding Rules -> Test & Qualita'](coding_rule.md), [.codex/CHECKLISTS](../.codex/CHECKLISTS.md).

---

## 7) Telemetria & sicurezza operativa

- Log centralizzati in `output/timmy-kb-<slug>/logs/` con formatter **key=value**.
- Redazione automatica dei segreti con `LOG_REDACTION=1`.
- Healthcheck caratteri/encoding: hook `fix-control-chars` / `forbid-control-chars` e script dedicato.
- Throttling retriever: warning `retriever.throttle.deadline` se il budget latenza si esaurisce; `candidate_limit` viene clampato e loggato.

Riferimenti: [README -> Telemetria & sicurezza](../README.md), [User Guide -> Controllo caratteri](user_guide.md).

---

## 8) Procedure GitHub (push/publish) & rollback

**Publish (CLI)**
```bash
py src/onboarding_full.py --slug <slug>
# pubblica solo i .md da book/ sul branch di destinazione
```

**Orchestrazione interna (regole)**
- Usa sempre gli helper Git: `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`.
- Nelle unit test, stubbare `_prepare_repo`/`_stage_changes` secondo gli esempi nei test.
- Lock GitHub configurabile via env: `TIMMY_GITHUB_LOCK_TIMEOUT_S`, `TIMMY_GITHUB_LOCK_POLL_S`, `TIMMY_GITHUB_LOCK_DIRNAME` (default 10s/0.25s/.github_push.lockdir).

**Rollback**
- **Push fallito (rete/rate):** `_push_with_retry` ripete con backoff; se esaurito, lascia stato locale coerente (ripetibile).
- **Divergenza branch:** usare `_force_push_with_lease` assicurando diff ristretto; aprire PR con spiegazione.
- **Contenuti non validi:** revert atomico del change set; ripetere preflight (solo `.md`, niente `.md.fp`).

Riferimenti: [.codex/AGENTS](../.codex/AGENTS.md).

---

## 9) Governance AGENTS & matrice

- **SSoT di policy:** [AGENTS Index](AGENTS_INDEX.md).
- Gli `AGENTS.md` locali (UI, Pipeline, Semantica, Test, Documentazione, Codex) contengono **solo override** e rimandano all'indice.
- Tenere allineata la **matrice** con `pre-commit run agents-matrix-check --all-files` quando si toccano gli `AGENTS.md`.
- La CI (`job build` in `.github/workflows/ci.yaml`) esegue `python tools/gen_agents_matrix.py --check` e fallisce se la matrice non e' aggiornata.

Riferimenti: [AGENTS Index](AGENTS_INDEX.md), [docs/AGENTS.md](AGENTS.md), [src/ui/AGENTS.md](../src/ui/AGENTS.md), [src/semantic/AGENTS.md](../src/semantic/AGENTS.md), [src/pipeline/AGENTS.md](../src/pipeline/AGENTS.md), [tests/AGENTS.md](../tests/AGENTS.md), [.codex/AGENTS.md](../.codex/AGENTS.md).

---

### Pattern operativi aggiuntivi (UI/Refactor)
- Nei moduli UI (es. preflight), adottare il pattern **Collector + Orchestratore**
  per separare raccolta check e coordinamento, mantenendo ordine e output invariati.
- I refactor devono essere **non-breaking**, mantenere firma e semantica dei messaggi,
  ed evitare side-effect a import-time.
- Il logging deve restare minimale e strutturato: eventi sintetici (`run_start`, `check_failed`, `run_complete`)
  senza includere dati sensibili (PII/segreti).

---

## 10) Operazioni UI (Streamlit)

- Router obbligatorio (`st.Page` + `st.navigation`); helper `ui.utils.route_state`/`ui.utils.slug` per deep-link.
- Gating **Semantica** solo con `raw/` presente.
- Messaggi utente brevi; dettagli a log.
- I/O solo tramite util SSoT; nessuna write manuale.

Riferimenti: [src/ui/AGENTS.md](../src/ui/AGENTS.md), [src/ui/pages/AGENTS.md](../src/ui/pages/AGENTS.md), [User Guide -> Guida UI](user_guide.md).

---

## 11) Vision Statement & strumenti AI

- Generazione mapping: `tools/gen_vision_yaml.py` produce `semantic/semantic_mapping.yaml` a partire da `config/VisionStatement.pdf`.
- La UI legge sempre il modello da `config/config.yaml` via `get_vision_model()` (SSoT).
- Preferire scenario **Agent**; *Full Access* solo con motivazione esplicita e branch dedicato.
- Health-check Vision (`tools/vision_alignment_check.py`) esporta `use_kb_source`, `strict_output_source`, `assistant_id`, `assistant_id_source`, `assistant_env` e `assistant_env_source` nell'output JSON (oltre ai log) per agevolare diagnosi end-to-end.
- `use_kb` segue lSSoT Settings/config con override opzionale `VISION_USE_KB` (0/false/no/off  False); le istruzioni runtime abilitano File Search solo se il flag risulta attivo.

Riferimenti: [User Guide -> Vision Statement](user_guide.md), [Developer Guide -> Configurazione](developer_guide.md).

---

## 12) Checklists operative (estratto)

- **PR/Commit:** conventional messages; test minimi aggiornati; 0 warning cSpell su `docs/`.
- **Sicurezza & I/O:** `ensure_within*` ovunque; scritture atomiche; rollback definito.
- **UI/Workflow:** Gating Semantica; Preview Docker sicura; SSoT `semantic/tags.db`.
- **Drive/Git:** credenziali presenti; push: **solo** `.md` da `book/`.
- **Documentazione (blocking):** per ogni cambio funzionale/firma/UX aggiornare Architecture/Developer Guide/User Guide (e `.codex/WORKFLOWS` se tocca pipeline) e indicare in PR `Docs: ...`; senza nota esplicita la review non passa.

Riferimenti: [.codex/CHECKLISTS](../.codex/CHECKLISTS.md).

---

## 13) Troubleshooting (rapido)

- **Drive non scarica PDF:** genera README in `raw/`, verifica permessi e `DRIVE_ID`.
- **Preview HonKit non parte:** controlla Docker e porta libera.
- **Conversione fallita (solo README/SUMMARY):** `raw/` privo di PDF validi o fuori perimetro (symlink).
- **Spell-check/docs mis-match:** esegui cSpell sui docs e riallinea titoli/frontmatter alla versione.
- **Modello non coerente:** verifica `config/config.yaml` e `get_vision_model()`.

Riferimenti: [User Guide -> Troubleshooting](user_guide.md).

---

## 14) ADR & cambi di design

- Qualsiasi decisione architetturale rilevante va registrata come **ADR** in `docs/adr/`.
- Aggiorna l'indice ADR e collega i documenti interessati; se superata, marca *Superseded* e link al successore.

Riferimenti: [docs/adr/README.md](adr/README.md).

---

## 15) Policy sintetiche (obbligatorie)

1. **SSoT & Safety:** utility obbligatorie per I/O; nessuna write fuori workspace cliente.
2. **Micro-PR:** modifiche piccole e motivate; se tocchi X, aggiorna Y/Z (docs/test/UX).
3. **UI import-safe:** nessun side-effect a import-time.
4. **Gating UX:** azioni guidate dallo stato (es. Semantica solo con RAW presente).
5. **Docs & Versioning:** allinea README/Docs/Frontmatter alla versione `v1.0 Beta`.
6. **Matrice AGENTS:** sempre aggiornata; esegui `agents-matrix-check` quando tocchi gli `AGENTS.md`.

---

## 16) Appendice: comandi utili

```bash
# UI
streamlit run onboarding_ui.py   # la UI imposta REPO_ROOT_DIR e lancia Streamlit dallo stesso repo

# Orchestrazione CLI
py src/pre_onboarding.py --slug <slug> --name "<Cliente>" --non-interactive
py src/tag_onboarding.py --slug <slug> --non-interactive --proceed
# Tuning NLP parallelo (worker auto se non specificato)
py src/tag_onboarding.py --slug <slug> --nlp --nlp-workers 6 --nlp-batch-size 8
py src/semantic_onboarding.py --slug <slug> --non-interactive
py src/onboarding_full.py --slug <slug> --non-interactive

# QA locale
make qa-safe
pytest -q
pre-commit run --all-files

# Spell & encoding
pre-commit run cspell --all-files
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files
```
