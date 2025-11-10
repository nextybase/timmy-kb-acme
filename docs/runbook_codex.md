# Runbook Codex - Timmy KB (v1.0 Beta)

> Questo runbook e' la guida **operativa** per lavorare in sicurezza ed efficacia sul repository **Timmy KB** con approccio *Agent-first* e supervisione **HiTL**. E' la fonte principale per i flussi quotidiani; i dettagli di design vivono negli altri documenti tecnici indicati nei rimandi.

- **Audience:** developer, tech writer, QA, maintainers, agent "Codex" (repo-aware).
- **Scope:** operazioni locali, UI/CLI, integrazioni OpenAI/Drive/GitHub, sicurezza I/O e path-safety, qualita', rollback e risoluzione problemi.
- **Rimandi canonici:** [Developer Guide](developer_guide.md), [Coding Rules](coding_rule.md), [Architecture Overview](architecture.md), [AGENTS Index](AGENTS_INDEX.md), [.codex/WORKFLOWS](../.codex/WORKFLOWS.md), [.codex/CHECKLISTS](../.codex/CHECKLISTS.md), [User Guide](user_guide.md).

---

## 1) Prerequisiti & setup rapido

**Tooling minimo**
- Python **>= 3.11**, `pip`, `pip-tools`; (opz.) **Docker** per preview HonKit.
  Vedi anche README -> *Prerequisiti rapidi*.
- Credenziali: `OPENAI_API_KEY` (o `OPENAI_API_KEY_FOLDER`), `GITHUB_TOKEN`; per Drive: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`.
- Pre-commit: `pre-commit install --hook-type pre-commit --hook-type pre-push`.

**Ambiente**
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt   # se serve Drive
make qa-safe
pytest -q
```
Riferimenti: [README](../README.md), [Developer Guide -> Dipendenze & QA](developer_guide.md).

---

## 2) Configurazione: `.env` (segreti) vs `config/config.yaml` (config)

- **SSoT:** segreti **fuori** repo in `.env`; configurazione applicativa **versionata** in `config/config.yaml`.
  Esempi e policy: [docs/configuration.md](configuration.md).

**Esempio corretto (`config/config.yaml`):**
```yaml
vision:
  model: gpt-4o-mini-2024-07-18
  assistant_id_env: OBNEXT_ASSISTANT_ID
retriever:
  candidate_limit: 3000
  latency_budget_ms: 300
```
**Regole operative**
- Le chiamate **dirette** leggono `vision.model` (UI/CLI).
- Il flusso **Assistant** usa l'ID letto da `vision.assistant_id_env` (ENV).
- La UI legge il modello tramite `get_vision_model()` (SSoT).

Riferimenti: [Developer Guide -> Configurazione](developer_guide.md), [Configuration](configuration.md).

---

## 3) Sicurezza & path-safety (vincolante)

- **Path-safety:** qualsiasi I/O passa da `pipeline.path_utils.ensure_within*`.
- **Scritture atomiche:** `pipeline.file_utils.safe_write_text/bytes` (temp + replace).
- **Logging strutturato:** `pipeline.logging_utils.get_structured_logger` con **redazione** segreti quando `LOG_REDACTION` e' attivo.
- **Cache RAW PDF:** `iter_safe_pdfs` usa cache LRU con TTL/cap configurabili in `config/config.yaml` (`raw_cache.ttl_seconds`/`max_entries`, override via `TIMMY_SAFE_PDF_CACHE_TTL` e `TIMMY_SAFE_PDF_CACHE_CAPACITY`); le scritture PDF con `safe_write_*` invalidano e pre-riscaldano la cache.
- **UI import-safe:** nessun side-effect a import-time; wrapper mantengono la **parita' di firma** col backend.

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

## 4) Flussi operativi (UI/CLI) - panoramica

> Obiettivo: trasformare PDF -> **KB Markdown AI-ready** con frontmatter coerente, README/SUMMARY, preview HonKit e push opzionale su GitHub.

**End-to-end (workflow standard)**
1. **pre_onboarding** -> crea workspace `output/timmy-kb-<slug>/...`, opz. provisioning Drive + upload config.
2. **tag_onboarding** -> `semantic/tags_raw.csv` + **checkpoint HiTL** -> `tags_reviewed.yaml` (authoring).
3. **semantic_onboarding** (via `semantic.api`) -> **PDF->Markdown** (`book/`), **frontmatter enrichment** (SSoT `semantic/tags.db`), **README/SUMMARY** e preview **Docker**.
4. **onboarding_full** -> preflight (solo `.md` in `book/`) -> **push GitHub**.

**Gating UX (UI)**
- La tab **Semantica** si abilita **solo** se `raw/` locale e' presente.
- Preview Docker: validazione porta e `container_name` sicuro.

Riferimenti: [.codex/WORKFLOWS](../.codex/WORKFLOWS.md), [User Guide](user_guide.md), [Architecture](architecture.md).

---

## 5) Scenari Codex (repository-aware)

> Lo scenario **Agent** e' predefinito; **Full Access** e' eccezione con branch dedicati. Chat "solo testo" e' possibile ma **non** effettua write/push.

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
- La CI (`job build` in `.github/workflows/ci.yaml`) esegue `python scripts/gen_agents_matrix.py --check` e fallisce se la matrice non e' aggiornata.

Riferimenti: [AGENTS Index](AGENTS_INDEX.md), [docs/AGENTS.md](AGENTS.md), [src/ui/AGENTS.md](../src/ui/AGENTS.md), [src/semantic/AGENTS.md](../src/semantic/AGENTS.md), [src/pipeline/AGENTS.md](../src/pipeline/AGENTS.md), [tests/AGENTS.md](../tests/AGENTS.md), [.codex/AGENTS.md](../.codex/AGENTS.md).

---

## 10) Operazioni UI (Streamlit)

- Router obbligatorio (`st.Page` + `st.navigation`); helper `ui.utils.route_state`/`ui.utils.slug` per deep-link.
- Gating **Semantica** solo con `raw/` presente.
- Messaggi utente brevi; dettagli a log.
- I/O solo tramite util SSoT; nessuna write manuale.

Riferimenti: [src/ui/AGENTS.md](../src/ui/AGENTS.md), [User Guide -> Guida UI](user_guide.md).

---

## 11) Vision Statement & strumenti AI

- Generazione mapping: `tools/gen_vision_yaml.py` produce `semantic/semantic_mapping.yaml` a partire da `config/VisionStatement.pdf`.
- La UI legge sempre il modello da `config/config.yaml` via `get_vision_model()` (SSoT).
- Preferire scenario **Agent**; *Full Access* solo con motivazione esplicita e branch dedicato.

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
streamlit run onboarding_ui.py

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
