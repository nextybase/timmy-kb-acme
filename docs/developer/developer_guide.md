# Developer Guide v1.0 Beta

## Executive summary

Questo testo accompagna chi costruisce il sistema, ricordando che il valore è nel disegnare condizioni epistemiche condivise, non nel consegnare soluzioni autonome: ogni scelta tecnica nasce dal confronto con un contesto incerto e ogni modifica aggiorna una narrativa di responsabilità collettiva.

Il ruolo del developer è presidiare vincoli, tracciare l'incertezza e rendere esplicito ciò che non è ancora deciso, mantenendo la propria autorità e lasciando che il sistema resti uno strumento di supporto, mai una sostituzione del giudizio umano.

Per la cornice filosofica del progetto vedi [MANIFEST.md](../../MANIFEST.md).

Guida per sviluppare e manutenere **Timmy KB** in modo coerente e sicuro. Questa versione è la base iniziale della documentazione tecnica: niente riferimenti a legacy o migrazioni passate.
Per un percorso rapido step-by-step vedi anche [Developer Quickstart](developer_quickstart.md).

---

## Obiettivi

- **SSoT (Single Source of Truth)** per configurazioni, dipendenze e utility condivise.
- **Logging strutturato centralizzato**, redazione automatica dei segreti, handler idempotenti.
- **Path-safety** e **scritture atomiche** per ogni I/O nel workspace cliente.
- **UI import-safe** (nessun side effect a import-time).
- **Parità di firma** tra wrapper/facade UI e backend `pipeline.*` / `semantic.*`.
- **Riproducibilità ambienti** tramite pin gestiti con `pip-tools` (requirements/constraints).

---

## ALERT / Workspace Discipline (non negoziabile)

- **Decisione Beta:** la repo root non deve mai diventare stato runtime; contiene solo artefacts versionati.
- **Definizioni (rigide):**
  - *Artefacts* = input versionati che determinano il comportamento (codice, config, policy, schemi).
  - *Derivatives* = output generati a runtime (output, log, cache, index, tmp, build).
- **Stop-the-line (Git):** se `git status` mostra file non tracciati o modificati fuori policy (fuori policy = qualsiasi file o directory non versionata che non sia codice, configurazione o documentazione), fermati e ripulisci.
- **Stop-the-line (ignored):** se `git status --ignored` o `git clean -ndx` mostra derivatives, fermati e rimuovili dal repo.
- **Decisione Beta:** vietati backup ad-hoc nel repo (`*.bak`, `.git.bak`, copie manuali, snapshot).
- **Runtime solo disposable:** ammesso solo se usa e getta, non richiesto per correttezza, e fuori dal repo.

---

## Agency & Control Plane

- **WHAT:** la governance agency-first (ProtoTimmy → Timmy, Domain Gatekeepers, Control Plane/OCP, Prompt Chain) è documentata in `instructions/*` e definisce chi decide, valida ed esegue.
- **HOW:** i moduli `pipeline.*`, `semantic.*`, `workspace_bootstrap` e `WorkspaceLayout` sono strumenti operativi per I/O, path, logging e semantica; garantiscono artefacts affidabili (markdown arricchiti + knowledge graph validato) ma non orchestrano né decidono.
- La pipeline di foundation “apre” Timmy quando produce gli artefacts richiesti e il knowledge graph viene validato; fino a quel momento ProtoTimmy guida la fondazione e OCP gestisce il control plane senza porsi come agency.
- Ogni riferimento a `pipeline.*` in questo documento va inteso come HOW (strumento tecnico); le decisioni e i gate sono descritte nelle sezioni `instructions/00*`, `instructions/01*` e `instructions/02*`.

---

## Architettura in breve

- **Pipeline** (`pipeline.*`): funzioni SSoT per I/O, path-safety, logging e semantica.
- **UI/Service Layer** (`src/ui/*`): presenta funzioni e schermate Streamlit, delega alla pipeline senza cambiare semantica.
- **Semantic** (`semantic.*`): conversione PDF→Markdown, arricchimento frontmatter, generazione `SUMMARY.md` / `README.md`.
- **Workspace cliente**: `output/timmy-kb-<slug>/` con sottocartelle `raw/`, `book/`, `semantic/`, `config/`, `logs/`.
- **DB KB per slug**: `semantic/kb.sqlite` vive nel workspace cliente e rappresenta l’unica sorgente supportata nel flusso 1.0.

---

## Configurazione (SSoT)

Il file `config/config.yaml` è la fonte unica per i parametri condivisi. Esempio per LLM **diretti**:

```yaml
ai:
  vision:
    model: gpt-4o-mini-2024-07-18   # modello per le chiamate dirette
    strict_output: true             # abilita validazioni strutturali quando necessario
    assistant_id_env: OBNEXT_ASSISTANT_ID  # usato solo dal flusso Assistant
```

**Regole:**
- Le **chiamate dirette** (Responses/Chat Completions) leggono sempre `ai.vision.model`.
- Il flusso **Assistant** usa l'ID letto dall'ambiente il cui nome è in `ai.vision.assistant_id_env`.
- Accesso runtime **solo** tramite `pipeline.settings.Settings` / `ClientContext.settings` (UI inclusa); niente letture YAML manuali.
- Config cliente: usare l’API unica prevista dal core (es. `pipeline.config_utils.load_client_settings(context)` / `context.settings` / `as_dict()`) ed evitare derivazioni ad-hoc.

Getter consigliato lato UI:

```python
from ui.config_store import get_vision_model

model = get_vision_model()  # passa sempre da Settings.load (SSoT)
```

### OIDC (opzionale)

- Configurare `security.oidc.*` in `config/config.yaml` usando riferimenti `*_env`.
- Impostare gli eventuali placeholder in `.env` (vedi `.env.example`).
- In CI GitHub, valorizza `GITHUB_OIDC_AUDIENCE` come Repository Variable per abilitare il probe (`tools/ci/oidc_probe.py`), che logga solo metadati (il token non viene mai loggato).

### GitBook API

- La preview usa HonKit via Docker ed è gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).

---

## Logging centralizzato

Usa sempre il logger strutturato della pipeline; vietati `print`, `logging.basicConfig` e `logging.getLogger(...)` nei moduli.

```python
from pipeline.logging_utils import get_structured_logger

log = get_structured_logger(__name__, run_id=None, context={"slug": "dummy"})
log.info("ui.preview.open", extra={"slug": "dummy", "page": "preview"})
```

**Caratteristiche:**
- Output in `output/timmy-kb-<slug>/logs/`.
- Redazione automatica di token/segreti quando `LOG_REDACTION` è attivo.
- Handler idempotenti (console/file), formatter key-value, `run_id` opzionale.

**Regola d'uso nei servizi/UI:** il logger viene creato per modulo e passato in call-chain dove necessario, evitando stati globali.

---

## Frontmatter (SSoT)

Per il parsing/dump del frontmatter Markdown e per letture con cache usa sempre `pipeline.frontmatter_utils`:

- `parse_frontmatter(text) -> (meta, body)` e `dump_frontmatter(meta)` sono l’SSoT.
- `read_frontmatter(base, path, use_cache=True)` effettua path-safety e caching (invalidazione su mtime/size).
- Evita implementazioni duplicate in moduli di dominio: delega ai wrapper compat già presenti.
- La cache del frontmatter `_FRONTMATTER_CACHE` è LRU bounded (256 entry): nei run lunghi/Streamlit è buona pratica chiamare `clear_frontmatter_cache()` quando rilasci workspace o dopo batch estesi.
- I workflow semantici orchestrati da `semantic.api` la svuotano automaticamente a fine run per garantire isolamento tra esecuzioni consecutive.

Esempio rapido:

```python
from pipeline.frontmatter_utils import read_frontmatter, dump_frontmatter

meta, body = read_frontmatter(base_dir, md_path)
new_text = dump_frontmatter({**meta, "title": "Nuovo titolo"}) + body
```

---

## Path-safety & I/O sicuro

Tutti i percorsi workspace derivano da `WorkspaceLayout`. Parti dallo slug, risolvi il layout (`get_ui_workspace_layout` nelle UI oppure `WorkspaceLayout.from_context(...)`) e usa direttamente `layout.raw_dir`, `layout.semantic_dir`, `layout.config_path`, `layout.tags_db`, `layout.vision_pdf`, ecc.

Costruire `output/timmy-kb-<slug>` manualmente è deprecato e può introdurre drift o vulnerabilità di path.

Prima di leggere o scrivere, risolvi il path con `pipeline.path_utils.ensure_within_and_resolve` e scrivi con writer atomici (`safe_write_text`, `safe_write_bytes`, ecc.).

```python
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.file_utils import safe_write_text
from ui.utils.workspace import get_ui_workspace_layout

layout = get_ui_workspace_layout(slug, require_env=False)
yaml_path = ensure_within_and_resolve(layout.semantic_dir, layout.semantic_dir / "tags_reviewed.yaml")
safe_write_text(yaml_path, content, encoding="utf-8", atomic=True, fsync=False)
```

### Golden path “slug → raw/semantic/tags”

```python
layout = get_ui_workspace_layout(slug, require_env=False)
raw_dir = layout.raw_dir
semantic_dir = layout.semantic_dir
tags_db = layout.tags_db
vision_pdf = layout.vision_pdf
```

È la sequenza consigliata per i nuovi moduli UI e servizi: risolvi il layout, usa i campi esposti, evita helper compat/legacy se il layout è già disponibile.

---

## Workspace SSoT (WorkspaceLayout)

Il progetto utilizza `WorkspaceLayout` come Single Source of Truth (SSoT) per tutti i percorsi derivati dallo slug del workspace. `WorkspaceLayout` sostituisce la costruzione manuale dei path e garantisce:
- coerenza tra CLI, UI e servizi,
- sicurezza dei path tramite `ensure_within` e `ensure_within_and_resolve`,
- riduzione del rischio di drift e regressioni,
- struttura prevedibile e uniforme dei workspace.

`WorkspaceLayout` viene sempre costruito a partire dal `ClientContext`: lo slug viene validato, il workspace radice viene risolto e tutti i percorsi (`raw/`, `semantic/`, `book/`, `logs/`, `config/`, `mapping/`) sono derivati in modo deterministico.

La risoluzione del workspace è **fail-fast**: in runtime non viene mai creato nessun file o directory “per sicurezza”. Le eccezioni dedicate (`WorkspaceNotFound`, `WorkspaceLayoutInvalid`, `WorkspaceLayoutInconsistent`) vengono propagate ai caller affinché possano loggare l’errore e fermare il flow.

### Modalità operative

- **RUNTIME:** il resolver fallisce con una delle tre eccezioni se lo slug non esiste, il layout manca di asset minimi o presenta inconsistenze; non è richiesta alcuna riparazione implicita e il caller non deve mai creare directory.
- **NEW_CLIENT_BOOTSTRAP / DUMMY_BOOTSTRAP:** i flussi `bootstrap_client_workspace` e `bootstrap_dummy_workspace` creano o rigenerano gli asset minimi.
- **MIGRATION_OR_MAINTENANCE:** `migrate_or_repair_workspace` è l’unico entrypoint autorizzato a interpretare `WorkspaceLayoutInconsistent` e riparare asset avanzati.

> The bootstrap APIs exposed by `pipeline.workspace_bootstrap` are the single source of truth for creating or repairing layouts; all other code must keep relying on `WorkspaceLayout` in fail-fast mode.

| Eccezione | Cause tipiche | Chi può riparare |
|-----------|--------------|------------------|
| `WorkspaceNotFound` | Slug non mappato o radice fisica assente | `bootstrap_client_workspace`, `bootstrap_dummy_workspace`, `migrate_or_repair_workspace` |
| `WorkspaceLayoutInvalid` | Mancano asset minimi (config/book/semantic) | `bootstrap_client_workspace`, `bootstrap_dummy_workspace`, `migrate_or_repair_workspace` |
| `WorkspaceLayoutInconsistent` | Config/versione/mapping incoerenti | `migrate_or_repair_workspace` |

---

## Retriever (ricerca)

- `search(...)` restituisce `list[SearchResult]` tipizzata (`content`, `meta`, `score`).
- Hardening errori: le eccezioni di embedding vengono intercettate e loggate come `retriever.query.embed_failed`, con ritorno `[]` per evitare crash negli orchestratori UI/CLI.
- Throttling: il guard emette `retriever.throttle.deadline` quando il budget latenza si esaurisce; `candidate_limit` configurato viene clampato e loggato.
- Il budget di latenza (`throttle.latency_budget_ms`) viene verificato prima di embedding e fetch dal DB: i call-site devono considerare `[]` anche come timeout/errore gestito e loggare l'evento utente se necessario.

---

## UI import-safe

- Nessun `load_dotenv()` o I/O a livello di modulo.
- Incapsula il caricamento env/config in helper idempotenti (es. `_maybe_load_dotenv()` in `ui.preflight`) e invocali **solo** nel runtime (funzioni `run_*`, servizi, orchestratori).
- I moduli devono essere importabili anche in ambienti headless/minimali.

---

## Wrapper & Facade: parità di firma (SSoT)

Qualsiasi wrapper UI che delega a `pipeline.*` / `semantic.*` **mantiene la stessa firma** (nomi, posizione, default). Nessuna modifica semantica dei default.

**Linee guida:**
1. Riesponi le nuove feature del backend **nello stesso commit** (es. nuovi flag `fsync`, `retry`, `atomic`).
2. Copertura con **test di parità firma** e **test passthrough** dei parametri.

---

## Gestione dipendenze (pip-tools)

- I pin vivono nei file generati `requirements*.txt` e `constraints.txt`.
- Modifichi **solo** i sorgenti `requirements*.in` e rigeneri con `pip-compile`.

---

## Qualità & CI

- Lint/format: `ruff`, `black`, `isort` (line-length 120).
- Type checking: `mypy`/`pyright`.
- Hook pre-commit: format/lint prima del commit; smoke test in CI.

---

# Definition of Done — v1.0 Beta (Determinismo / Low Entropy)

## Principio

Per la Beta, il determinismo è richiesto nei processi e nella gestione degli artefatti.
Le degradazioni sono ammesse solo se:
1) deterministiche, 2) osservabili, 3) disambiguabili.

## Retriever: contratto minimo di osservabilità

1) Ogni query emette `retriever.query.started` con `response_id` e campi base.
2) Ogni fetch emette `retriever.candidates.fetched` includendo `budget_hit` e contatori.
3) Ogni ritorno `[]` è disambiguato da almeno un evento tra:
   - deadline/budget (`retriever.throttle.deadline`, `retriever.latency_budget.hit`)
   - errore embedding gestito (`retriever.query.embed_failed`)
   - input invalid/skipped (`retriever.query.invalid`, `retriever.query.skipped`)
4) Nessuna degradazione silenziosa: se un controllo fallisce, deve esistere un evento esplicito.

## Waiver

È possibile accettare una non-conformità solo se:
- è documentata nel PR,
- ha un issue linkato,
- non è silenziosa (log/evento presente),
- non altera artefatti in modo non deterministico.

---

## Contributi

- PR piccole, commit atomici, messaggi chiari (imperativo al presente).
- Ogni modifica di comportamento va coperta da test.

