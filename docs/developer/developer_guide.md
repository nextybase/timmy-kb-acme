# Developer Guide  v1.0 Beta

Executive summary

Questo testo accompagna chi costruisce il sistema, ricordando che il valore è nel disegnare condizioni epistemiche condivise, non nel consegnare soluzioni autonome: ogni scelta tecnica nasce dal confronto con un contesto incerto e ogni modifica aggiorna una narrativa di responsabilità collettiva.

Il ruolo del developer è presidiare vincoli, tracciare l'incertezza e rendere esplicito ciò che non è ancora deciso, mantenendo la propria autorità e lasciando che il sistema resti uno strumento di supporto, mai una sostituzione del giudizio umano.

Per la cornice filosofica del progetto vedi [MANIFEST.md](../../MANIFEST.md).

Guida per sviluppare e manutenere **Timmy KB** in modo coerente e sicuro. Questa versione e la base iniziale della documentazione tecnica: niente riferimenti a legacy o migrazioni passate.
Per un percorso rapido step-by-step vedi anche [Developer Quickstart](developer_quickstart.md).

---

## Obiettivi
- **SSoT (Single Source of Truth)** per configurazioni, dipendenze e utility condivise.
- **Logging strutturato centralizzato**, redazione automatica dei segreti, handler idempotenti.
- **Path-safety** e **scritture atomiche** per ogni I/O nel workspace cliente.
- **UI import-safe** (nessun sideeffect a import-time).
- - **Parita di firma** tra wrapper/facade UI e backend `pipeline.*`/`semantic.*`.
- - **Riproducibilita ambienti** tramite pin gestiti con `pip-tools` (requirements/constraints).
-
---

## ALERT / Workspace Discipline (non negoziabile)
- **Decisione Beta:** la repo root non deve mai diventare stato runtime; contiene solo artefacts versionati.
- **Definizioni (rigide):** artefacts = input versionati che determinano il comportamento (codice, config, policy, schemi). Derivatives = output generati a runtime (output, log, cache, index, tmp, build).
- **Stop-the-line (Git):** se `git status` mostra file non tracciati o modificati fuori policy (fuori policy = qualsiasi file o directory non versionata che non sia codice, configurazione o documentazione), fermati e ripulisci.
- **Stop-the-line (ignored):** se `git status --ignored` o `git clean -ndx` mostra derivatives, fermati e rimuovili dal repo.
- **Decisione Beta:** vietati backup ad-hoc nel repo (`*.bak`, `.git.bak`, copie manuali, snapshot).
- **Runtime solo disposable:** ammesso solo se usa e getta, non richiesto per correttezza, e fuori dal repo.

## Agency & Control Plane
- WHAT: la governance agency-first (ProtoTimmy → Timmy, Domain Gatekeepers, Control Plane/OCP, Prompt Chain) è documentata in `instructions/*` e definisce chi decide, valida ed esegue.
- HOW: i moduli `pipeline.*`, `semantic.*`, `workspace_bootstrap` e `WorkspaceLayout` sono strumenti operativi per I/O, path, logging e semantica; garantiscono artifact affidabili (markdown arricchiti + knowledge graph validato) ma non orchestrano né decidono.
- La pipeline di foundation apre Timmy quando produce gli artifact richiesti e il knowledge graph viene validato; fino a quel momento ProtoTimmy guida la fondazione e OCP gestisce il control plane senza porsi come agency.
- Ogni riferimento a `pipeline.*` in questo documento va inteso come HOW (strumento tecnico); le decisioni e i gate sono descritte nelle sezioni `instructions/00*`, `instructions/01*` e `instructions/02*`.

## Architettura in breve
- **Pipeline** (`pipeline.*`): funzioni SSoT per I/O, path-safety, logging e semantica.
- **UI/Service Layer** (`src/ui/*`): presenta funzioni e schermate Streamlit, delega alla pipeline senza cambiare semantica.
- **Semantic** (`semantic.*`): conversione PDFMarkdown, arricchimento frontmatter, generazione `SUMMARY.md`/`README.md`.
- **Workspace cliente**: `output/timmy-kb-<slug>/` con sottocartelle `raw/`, `book/`, `semantic/`, `config/`, `logs/`.
- **DB KB per slug**: `semantic/kb.sqlite` vive nel workspace cliente e rappresenta l’unica sorgente supportata nel flusso 1.0.

---

## Configurazione (SSoT)
Il file `config/config.yaml` e la fonte unica per i parametri condivisi. Esempio per LLM **diretti**:

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
- Config cliente: API unica `pipeline.config_utils.load_client_settings(context)` ? `context.settings` ? `.as_dict()` per le UI/CLI.

Getter consigliato lato UI:

```python
from ui.config_store import get_vision_model

model = get_vision_model()  # passa sempre da Settings.load (SSoT)
```

### OIDC (opzionale)
- Configurare `security.oidc.*` in `config/config.yaml` usando riferimenti `*_env`.
- Impostare gli eventuali placeholder in `.env` (vedi `.env.example`).
- In CI GitHub, valorizza `GITHUB_OIDC_AUDIENCE` come Repository Variable per abilitare il probe (`tools/ci/oidc_probe.py`), che logga solo metadati (`has_token` non include il token).

### GitBook API

- La preview usa HonKit via Docker ed e gestita via adapter/UI; il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview` (vedi runbook).

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
- Redazione automatica di token/segreti quando `LOG_REDACTION` e attivo.
- Handler idempotenti (console/file), formatter key-value, `run_id` opzionale.

**Regola d'uso nei servizi/UI:** il logger viene creato per modulo e passato in call-chain dove necessario, evitando stati globali.


## Frontmatter (SSoT)
Per il parsing/dump del frontmatter Markdown e per letture con cache usa sempre
`pipeline.frontmatter_utils`:

- `parse_frontmatter(text) -> (meta, body)` e `dump_frontmatter(meta)` sono lSSoT.
- `read_frontmatter(base, path, use_cache=True)` effettua path-safety e caching (invalidazione su mtime/size).
- Evita implementazioni duplicate in moduli di dominio: delega ai wrapper compat gia presenti.
- La cache del frontmatter `_FRONTMATTER_CACHE` e LRU bounded (256 entry): nei run lunghi/Streamlit resta buona pratica chiamare `clear_frontmatter_cache()` quando rilasci workspace o dopo batch estesi; i workflow semantici orchestrati da `semantic.api` la svuotano automaticamente a fine run per garantire isolamento tra esecuzioni consecutive.
- Ogni conversione emette log `debug` con evento `pipeline.frontmatter_cache.stats` (e `semantic.frontmatter_cache.stats_before_clear` prima del reset orchestrato) per diagnosticare l'occupazione della cache senza intaccare la pipeline.

Esempio rapido:
```python
from pipeline.frontmatter_utils import read_frontmatter, dump_frontmatter
meta, body = read_frontmatter(base_dir, md_path)
new_text = dump_frontmatter({**meta, "title": "Nuovo titolo"}) + body
```

Nota cache: dopo le scritture il frontmatter viene riallineato nella cache LRU (256 entry); i workflow semantici svuotano la cache a fine run, mentre negli altri flussi resta consigliata una chiamata esplicita a `clear_frontmatter_cache()` dopo batch estesi per liberare memoria.

------

## Path-safety & IO sicuro
Tutti i percorsi workspace derivano da `WorkspaceLayout`. Parti dallo slug, risolvi il layout (`get_ui_workspace_layout` nelle UI oppure `WorkspaceLayout.from_context/...`) e usa direttamente `layout.raw_dir`, `layout.semantic_dir`, `layout.config_path`, `layout.tags_db`, `layout.vision_pdf`, ecc. Costruire `output/timmy-kb-<slug>` manualmente è deprecato e può introdurre drift o vulnerabilità di path.

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

È la sequenza consigliata per i nuovi moduli UI e servizi: risolvi il layout, usa i campi esposti, evita helper legacy (`resolve_raw_dir`, `workspace_root`) se il layout è già disponibile.

 ---

## Workspace SSoT (WorkspaceLayout)

Il progetto utilizza WorkspaceLayout come Single Source of Truth (SSoT) per tutti i percorsi derivati dallo slug del workspace. WorkspaceLayout sostituisce la costruzione manuale dei path e garantisce:
- coerenza tra CLI, UI e servizi,
- sicurezza dei path tramite `ensure_within` e `ensure_within_and_resolve`,
- riduzione del rischio di drift e regressioni,
- struttura prevedibile e uniforme dei workspace.

WorkspaceLayout viene sempre costruito a partire dal `ClientContext`: lo slug viene validato, il workspace radice viene risolto e tutti i percorsi (`raw/`, `semantic/`, `book/`, `logs/`, `config/`, `mapping/`) sono derivati in modo deterministico. `from_context`, `from_slug` e `from_workspace` applicano la Workspace Layout Resolution Policy fail-fast: in fase di runtime non viene mai creato nessun file o directory “per sicurezza”, e le eccezioni dedicate (`WorkspaceNotFound`, `WorkspaceLayoutInvalid`, `WorkspaceLayoutInconsistent`) vengono propagate ai caller affinché possano loggare l’errore e fermare il flow.

### Modalità operative
- **RUNTIME**: il resolver fallisce con una delle tre eccezioni se lo slug non esiste, il layout manca di asset minimi o presenta inconsistenze; non è richiesta alcuna riparazione implicita e il caller non deve mai creare directory.
- **NEW_CLIENT_BOOTSTRAP / DUMMY_BOOTSTRAP**: i flussi `bootstrap_client_workspace` e `bootstrap_dummy_workspace` rilevano gli errori raccolti da WorkspaceLayout e si occupano di creare o rigenerare gli asset minimi, sfruttando la diagnostica per capire se un `WorkspaceLayoutInvalid` o `WorkspaceNotFound` indica un workspace inesistente o corrotto.
    - `bootstrap_client_workspace(context: ClientContext)` (modulo `pipeline.workspace_bootstrap`) implementa oggi il happy path NEW_CLIENT: crea/completa `output/timmy-kb-<slug>` con config/book/raw/semantic/logs minimi e lascia la validazione finale a `WorkspaceLayout`; il CLI `pre_onboarding` delega il workspace bootstrap a questa API, mentre il runtime normale non la invoca direttamente.
    - `migrate_or_repair_workspace(context: ClientContext)` (stesso modulo) è ora disponibile per flussi MIGRATION/MAINTENANCE che devono riparare asset minimi di un workspace esistente (config book raw semantic logs) prima di passare alle pipeline semantic/tag/drive più invasive.
    - I compat lato UI (`workspace_root`, `resolve_raw_dir`) sono stati disabilitati e sollevano sempre errori CHIARI: la UI deve risolvere il layout tramite `WorkspaceLayout` o `get_ui_workspace_layout` e, quando serve creare o riparare, delegare esplicitamente a `pipeline.workspace_bootstrap.bootstrap_client_workspace`, `bootstrap_dummy_workspace` o `migrate_or_repair_workspace`.
    - La pagina **Nuovo cliente** chiama esplicitamente `pipeline.workspace_bootstrap.bootstrap_client_workspace` per creare il workspace e mostra messaggi fail-fast se qualcosa non quadra; la pagina **Gestisci** offre un pulsante “Ripara workspace” che invoca `pipeline.workspace_bootstrap.migrate_or_repair_workspace` e ferma il runtime se il layout resta invalido. Il runtime UI non crea mai directory al di fuori di questi flussi autorizzati.
    - I flussi Drive/Vision-first (p.es. `build_drive_from_mapping` e `emit_readmes_for_raw`) riutilizzano oggi i campi `drive_folder_id`, `drive_raw_folder_id` e `drive_contrattualistica_folder_id` già scritti in `config.yaml` e li passano a `pipeline.drive.upload.create_drive_structure_from_yaml`, che aggiunge le sole sottocartelle mancanti sotto il `raw` esistente invece di tentare di ricrearlo da zero.
- **MIGRATION_OR_MAINTENANCE**: `migrate_or_repair_workspace` è l'unico entrypoint autorizzato a interpretare `WorkspaceLayoutInconsistent`, aggiornare schema/mapping o riparare asset semantic avanzati; in runtime lo stesso errore blocca il flow e richiede intervento umano o automazione controllata.

La risoluzione del workspace è dunque sempre fail-fast: i richiamanti ottengono i path solo se il layout è integralmente valido, mentre la creazione e la riparazione rimangono responsabilità dei flussi autorizzati.
`bootstrap_dummy_workspace` dal modulo `pipeline.workspace_bootstrap` è ora disponibile per generare un workspace dummy minimale conforme agli asset richiesti da `WorkspaceLayout`; questo flusso è destinato a smoke/dev locali, non alla produzione.

The bootstrap APIs exposed by `pipeline.workspace_bootstrap` are the single source of truth for creating or repairing layouts; all other code must keep relying on `WorkspaceLayout` in fail-fast mode.

| Eccezione | Cause tipiche | Chi può riparare |
|-----------|--------------|------------------|
| `WorkspaceNotFound` | Slug non mappato o radice fisica assente | `bootstrap_client_workspace`, `bootstrap_dummy_workspace`, `migrate_or_repair_workspace` |
| `WorkspaceLayoutInvalid` | Mancano `config/config.yaml`, `book/README.md`, `book/SUMMARY.md` o la directory `semantic/` | `bootstrap_client_workspace`, `bootstrap_dummy_workspace`, `migrate_or_repair_workspace` |
| `WorkspaceLayoutInconsistent` | Layout presente ma con config/versione/mapping semantic incoerenti rispetto ai metadati | `migrate_or_repair_workspace` |

Ogni nuovo modulo che necessita di percorsi workspace deve passare da questo flusso.

```
slug -> ClientContext.load() -> WorkspaceLayout.from_context()

workspace_path -> WorkspaceLayout.from_workspace()
```

Esempio aggiornato:

```python
layout = WorkspaceLayout.from_context(context)
semantic_dir = layout.semantic_dir
log_file = layout.log_file
tags_db = layout.tags_db
vision_pdf = layout.vision_pdf
```

Ogni componente deve evitare di ricostruire `raw_dir`, `semantic_dir` o `logs_dir` partendo da `base_dir / "..."` o `output/timmy-kb-<slug>`. L'uso di join manuali o concatenazioni di stringhe per ottenere i percorsi del workspace è deprecato e espone il codice a rischi di incoerenza e vulnerabilità sui path.

Questo approccio centralizzato rende più semplice la manutenzione e i refactor perché la logica dei path è vincolata a un’unica API con controlli di sicurezza condivisi.

---

## Retriever (ricerca)
- `search(...)` restituisce `list[SearchResult]` tipizzata (`content`, `meta`, `score`).
- Hardening errori: le eccezioni di embedding vengono intercettate e loggate come `retriever.query.embed_failed`, con ritorno `[]` per evitare crash negli orchestratori UI/CLI.
- Throttling: il guard emette `retriever.throttle.deadline` quando il budget latenza si esaurisce; `candidate_limit` configurato viene clampato e loggato.
- Il budget di latenza (`throttle.latency_budget_ms`) ora viene verificato prima di embedding e fetch dal DB: i call-site devono considerare `[]` anche come timeout/errore gestito e loggare l'evento utente se necessario.

---

## UI import-safe
- Nessun `load_dotenv()` o I/O a livello di modulo.
- Incapsula il caricamento env/config in helper idempotenti (es. `_maybe_load_dotenv()` in `ui.preflight`) e invocali **solo** nel runtime (funzioni `run_*`, servizi, orchestratori).
- I moduli devono essere importabili anche in ambienti headless/minimali.

---

## Wrapper & Facade: parita di firma (SSoT)
Qualsiasi wrapper UI che delega a `pipeline.*`/`semantic.*` **mantiene la stessa firma** (nomi, posizione, default). Nessuna modifica semantica dei default.

**Linee guida:**
1. Riesponi le nuove feature del backend **nello stesso commit** (es. nuovi flag `fsync`, `retry`, `atomic`).
2. Copertura con **test di parita firma** e **test passthrough** dei parametri.

```python
# Esempio test di parita firma
import importlib, inspect

def _sig(fn):  # rappresentazione semplice della firma
    return tuple((p.kind, p.name, p.default is not inspect._empty) for p in inspect.signature(fn).parameters.values())

def test_safe_write_text_signature_matches_backend():
    ui = importlib.import_module('ui.utils.core')
    be = importlib.import_module('pipeline.file_utils')
    assert _sig(ui.safe_write_text) == _sig(be.safe_write_text)
```

---

## Gestione dipendenze (pip-tools)
- I pin vivono nei file generati `requirements*.txt` e `constraints.txt`.
- Modifichi **solo** i sorgenti `requirements*.in` e rigeneri con `pip-compile`.

```bash
# Runtime / Dev / Opzionali
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt

# Rigenerazione pin
pip-compile requirements.in
pip-compile requirements-dev.in
pip-compile requirements-optional.in
```

**Extras opzionali** (ambienti non pin-locked): `pip install .[drive]` oppure `pip install -e ".[drive]"` in sviluppo.

---

## Qualita & CI
- Lint/format obbligatori: `ruff`, `black`, `isort` (line-length 120).
- Type checking consigliato: `mypy`/`pyright`.
- Hook pre-commit: format/lint prima del commit; smoke test in CI.

```bash
pre-commit install --hook-type pre-commit
make qa-safe     # isort/black/ruff/mypy (se presenti)
make ci-safe     # qa-safe + pytest
# Ambientesenza install: esegui i test con PYTHONPATH=src pytest -q
```

## ⚠️ Beta: Strict vs Dummy mode

Durante la Beta, il flusso di *`tag_onboarding`* è **strict by default**:
la generazione degli stub semantici è **bloccata** e lo stato massimo
raggiungibile è `TAGS_CSV_READY`.

L’esecuzione end-to-end con stub è consentita **solo** tramite flag esplicito
`--dummy` ed è sempre **tracciata nel _Decision Ledger_**.

👉 Per i dettagli operativi e le implicazioni di audit, vedi  
**[Strict vs Dummy – Guida Operativa](../strict_vs_dummy_beta.md)**.

## ✅ Beta: State Model (Decision Ledger = SSoT)

In Beta, il `workspace_state` è derivato esclusivamente dal Decision Ledger (SSoT).
Lo stato canonico è ancorato alla `latest_run` (regressione ammessa).
Nessun motore di stato separato: niente ricomposizioni tra run.
Il modello di stato è la specifica per stati, transizioni e regole di derivazione.
Usalo per interpretare il ledger in modo deterministico.
👉 **[State Model (Beta 1.0)](state_model.md)**.


## Product-grade tools
### Import policy, feature gating, fail-fast rules

Questa sezione definisce gli **standard obbligatori** per tutti i *tools di prodotto*
(script, generatori, smoke, maintenance) inclusi nello stack Timmy-KB.

I tools **non sono utilita di sviluppo**: fanno parte del prodotto e devono rispettare
gli stessi requisiti del core (pipeline, CLI, UI) in termini di **determinismo,
auditabilita e bassa entropia**.

Il file `tools/gen_dummy_kb.py` e il **riferimento canonico** per l'implementazione
di questi standard.

---

### Principio generale

Un tool di prodotto **non puo cambiare comportamento a causa di incidenti**
(bug, import falliti, dipendenze rotte).

Un cambiamento di comportamento e ammesso **solo** quando deriva da:
- feature intenzionalmente abilitate/disabilitate;
- configurazione esplicita;
- flag dichiarati.

Sono vietate:
- degradazioni silenziose;
- modalita implicite;
- fallback non dichiarati.

---

### Import policy

#### Dipendenze richieste (required)

Le dipendenze che fanno parte dello stack predeterminato (es. `yaml`,
`pipeline.env_utils`, `pipeline.file_utils`) **devono essere sempre presenti**.

Regole:
- se l'import fallisce -> **fail-fast immediato**;
- nessuno shim o implementazione alternativa;
- errore chiaro che segnali installazione incompleta o corrotta.

#### Feature opzionali

Una feature e opzionale **solo se e parte del contratto di prodotto**
(es. integrazione Drive).

Regole:
- sugli import opzionali e ammesso **solo**
  `ImportError` / `ModuleNotFoundError`;
- qualunque altra eccezione deve propagare (bug = stop);
- l'assenza della feature deve essere trattata come *feature non disponibile*,
  non come errore generico.

E vietato:
- usare `except Exception` sugli import;
- disabilitare feature per cause accidentali.

---

### Feature gating esplicito

Ogni tool di prodotto deve determinare **una sola volta all'avvio**
la propria modalita di esecuzione.

La decisione puo dipendere esclusivamente da:
- flag espliciti (es. `--with-drive`, `--no-drive`);
- configurazione;
- disponibilita prevista dei moduli.

Esempio (Drive):
- `auto`: Drive abilitato solo se modulo e prerequisiti sono presenti;
- `force_on`: Drive obbligatorio -> se non attivabile, errore;
- `force_off`: Drive sempre disabilitato.

La modalita **non deve mai cambiare durante l'esecuzione**.

---

### Runtime preflight deterministico

Ogni tool deve eseguire un **preflight deterministico** che produca uno stato
di runtime esplicito (es. `RuntimeMode`) contenente:
- modalita di esecuzione;
- motivazioni delle scelte;
- matrice delle feature disponibili.

Il preflight:
- non ha side-effect;
- e riproducibile a parita di configurazione;
- governa l'intera esecuzione del tool.

---

### Summary one-line obbligatorio

Ogni tool di prodotto deve emettere:
- una **summary one-line** all'inizio;
- la **stessa summary** alla fine dell'esecuzione.

La summary deve indicare almeno:
- stato delle feature principali (es. Drive, cleanup, registry);
- motivazioni delle eventuali disabilitazioni.

Esempio:
```
gen_dummy_kb.mode drive=OFF reason=missing DRIVE_ID,SERVICE_ACCOUNT_FILE; cleanup=ON; registry=OFF
```

Questo garantisce auditabilita, confrontabilita tra run e diagnosi rapida.

---

### Fail-fast come regola

Un tool di prodotto **deve terminare immediatamente** quando:
- una dipendenza required e mancante;
- una feature richiesta esplicitamente non e attivabile;
- un import fallisce per cause non previste;
- viene violato il contratto dichiarato.

E vietato:
- "andare avanti lo stesso";
- mascherare errori come modalita alternative;
- introdurre retrocompatibilità o shim non necessari.

---

### Riferimento

`tools/gen_dummy_kb.py` costituisce il **baseline ufficiale**
per la qualita dei tools di prodotto.

Ogni nuovo tool **deve allinearsi a questo modello**.

## Semantic content extraction
### Prod vs Dummy/Test: execution contract

Questa sezione definisce il **contratto operativo** per l'estrazione dei contenuti
(in particolare PDF e componenti NLP) all'interno della pipeline semantica.

L'obiettivo e garantire **determinismo e bassa entropia in produzione**, mantenendo
al contempo modalita di bootstrap, dummy e testing esplicitamente dichiarate.

---

### Principio generale

L'estrazione dei contenuti semantici (es. testo da PDF) **influisce direttamente**
sugli artefatti di enrichment (chunk, excerpt, ranking, tagging).

Di conseguenza:
- in **Produzione** l'estrazione e parte del core semantico;
- in **Dummy/Test** puo essere degradata *solo se dichiarato esplicitamente*.

E vietato qualsiasi comportamento "best-effort" non governato da un flag o da una modalita esplicita.

---

### Modalita di esecuzione

#### Produzione (Prod)

In modalita Produzione:
- i moduli di estrazione (PDF/NLP) sono **dipendenze richieste**;
- l'assenza di un modulo o un fallimento di estrazione **deve causare fail-fast**;
- non sono ammessi fallback silenziosi (`None`, output vuoto, log a livello debug).

Se l'estrazione non e possibile secondo contratto, la pipeline **deve terminare**
con errore esplicito e tracciabile.

---

#### Dummy / Test / Bootstrap

In modalita Dummy/Test:
- e ammesso un comportamento *best-effort* sull'estrazione dei contenuti;
- l'estrazione puo essere:
  - disabilitata,
  - parzialmente disponibile,
  - sostituita da fallback semantici di base.

Questa modalita e valida **solo se attivata esplicitamente** tramite flag o contesto
(es. `Disabilita Enrichment`, `Disabilita Semantic`, modalita Dummy KB).

Il sistema deve:
- dichiarare chiaramente la modalita in uso;
- tracciarla nei log e nella summary di esecuzione;
- evitare che questa modalita emerga per incidente (import falliti, eccezioni generiche).

---

### Regole di implementazione

- Gli import dei moduli di estrazione in **Prod** devono essere strict
  (`ImportError` / `ModuleNotFoundError` -> stop).
- I fallback (es. ritorno `None` o contenuto vuoto) sono ammessi **solo** in modalita
  Dummy/Test dichiarata.
- E vietato catturare `Exception` per degradare automaticamente il comportamento.
- Ogni run deve rendere visibile:
  - modalita (Prod vs Dummy/Test),
  - stato dell'estrazione,
  - motivazione di eventuali disabilitazioni.

---

### Riferimento

Queste regole si applicano a tutta la pipeline di content extraction
(es. funzioni di estrazione PDF, NLP utilities, chunking iniziale)
e sono complementari alle regole sui *product-grade tools*.

## Interfacciarsi correttamente agli Assistant OpenAI con l'SDK interno

Questa sezione descrive il modo corretto per collegare gli script del framework NeXT agli assistant OpenAI usando lo SDK interno (`ai.client_factory`, `client.responses.create`, modello-only).

### 7.1 Architettura di riferimento
- Recupero delle impostazioni dal `config.yaml` tramite `Settings()`.
- Risoluzione dell'`assistant_id` se richiesto (assistant_env -> variabile ambiente).
- Risoluzione del modello da config, con fallback al modello dell'assistant quando previsto. Segnale: nessun segnale/log esplicito documentato.
- Uso dell'SDK OpenAI centralizzato:
  ```python
  from ai.client_factory import make_openai_client
  client = make_openai_client()
  ```
- Chiamata tramite Responses API se serve output strutturato JSON.
- Validazione dell'output: mai fidarsi ciecamente del modello.

### 7.2 Best practice per i messaggi (Responses API)
Formato compatibile:
```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "contenuto..."}
        ],
    }
]
```
⚠️ Non usare `type: text` (gli assistant lo ignorano o generano errori).

### 7.3 Chiamata standard a `client.responses.create()`
```python
response = client.responses.create(
    model=model_name,
    input=messages,
    response_format={"type": "json_object"},
    temperature=0,
)
```
Note:
- `response_format` deve essere esattamente `{"type": "json_object"}` se ci aspettiamo JSON.
- L'output va letto da `response.output` o `response.output_text`.
```python
text = None
for item in response.output:
    if item.type == "output_text":
        text = item.text.value
        break
```

### 7.4 Regole per gli assistant
- L'assistant e solo contenitore di configurazione: niente thread, run, file upload.
- L'inferenza usa sempre Responses API (o completions modello-only).
- Dalle settings si leggono: `assistant_id_env` e `model` se configurato.
- Logica NeXT: assistant = definizione; Responses = inferenza.

### 7.5 Risoluzione del modello (`_resolve_kgraph_model` pattern)
- Se nel `config.yaml` esiste un modello esplicito -> usare quello.
- Se manca -> recuperare il modello dell'assistant (se presente).
- Se manca anche quello -> lanciare `ConfigError`.

### 7.6 Errori tipici e fix
Errore | Significato | Fix
--- | --- | ---
`Responses.create() got an unexpected keyword argument 'response_format'` | SDK troppo vecchio | Aggiornare `openai>=1.50`
`Invalid value: 'text'. Supported values are ...` | `type` errato nei messaggi | Usare `input_text`
JSON non valido | Il modello ha risposto in linguaggio naturale | Rafforzare prompt + validazione

### 7.7 Modello-only: quando usarlo
- Tutti gli script che non richiedono un assistant dedicato devono usare i modelli direttamente:
  ```python
  client.responses.create(model="gpt-4.1", input=messages)
  ```
- Esempi: Vision, ping ProtoTimmy, test diagnostici.

### 7.8 Logging e debug raccomandati
- Loggare sempre: modello usato, path input, `assistant_id` se usato, sample dell'output grezzo (non sensibile).
```python
logger.info("debug.raw_output", extra={"sample": text[:500]})
```

### Prompt Chain & agenti (vista sviluppatore)
- Lifecycle e ruoli (Planner/OCP/Codex): vedi [`system/specs/promptchain_spec.md`](../../system/specs/promptchain_spec.md) (SSoT).
- Active Rules, template e QA gates: vedi [`.codex/PROMPTS.md`](../../.codex/PROMPTS.md) e [`docs/policies/guida_codex.md`](../policies/guida_codex.md).
- Workflow OCP e gate: vedi [`docs/policies/OCP_WORKFLOW.md`](../policies/OCP_WORKFLOW.md).

---

## Test: piramide e casi minimi
- **Unit**  **contract/middle**  **smoke E2E** (dataset dummy; nessuna rete).
- Nota UI Beta 1.0: vedi `docs/policies/guida_codex.md` (sezione "UI testing stance (Beta 1.0)").
- Casi minimi obbligatori:
  - Slug invalidi (devono essere scartati/validati).
  - Traversal via symlink in `raw/` (gli helper non devono attraversare).
  - Parita di firma wrapper UI  backend e passthrough dei parametri.
  - Invarianti su `book/` (presenza `README.md`/`SUMMARY.md` dopo onboarding).

### Dummy KB (smoke E2E)
- CLI: `python tools/gen_dummy_kb.py --slug dummy --no-drive` (usa workspace in `output/` o `--base-dir <tmp>`; nessuna dipendenza Drive).
- Pipeline: **Vision → Semantic → Tags → RAW → Registry UI** (registro opzionale in `clients_db/clients.yaml`, rispettando gli override `CLIENTS_DB_*`/`REPO_ROOT_DIR`).
- Health report nel payload JSON (`health`): `vision_status` (`ok`/`error`/`timeout`), `fallback_used`, `raw_pdf_count`, `tags_count`, `mapping_valid`, `summary_exists`, `readmes_count`.
- Struttura minima generata: `config/config.yaml`, `semantic/{semantic_mapping.yaml,cartelle_raw.yaml,tags.db}`, `book/{README.md,SUMMARY.md}`, almeno un PDF valido in `raw/`.
- Rigenerazione sicura: la CLI esegue il cleanup locale prima di ogni run; per reset manuale usare `tools.clean_client_workspace.perform_cleanup` o cancellare `output/timmy-kb-<slug>`/override `--base-dir`.

#### Deep testing contract (operational)
- `smoke` è il percorso cablato descritto sopra; `deep` è la stessa pipeline con Vision e Drive attivi, senza fallback e con fresh secrets.
- Il flag CLI `--deep-testing` (anche la checkbox "Attiva testing profondo" nella UI) imposta `health.mode="deep"` nel payload finale e attiva hard check Vision/Drive.
- Se Vision/Drive falliscono, la run termina con `health.status="failed"`, `errors` descrive che "secrets/permessi non pronti" e viene emesso un evento `HardCheckError` visibile nella UI/dai logs.
- In deep vengono aggiunti `health.checks`, `health.external_checks`, e la sezione `golden_pdf` (path/sha256/bytes del PDF deterministico generato). Questi campi **non** devono apparire in smoke.
- Il messaggio vicino alla checkbox ricorda di consultare la pagina Secrets Healthcheck: una failure deep è un indicatore di permessi mancanti, non un bug della pipeline.

Esempio - smoke OK:
```json
{
  "mode": "smoke",
  "status": "ok",
  "vision_status": "ok",
  "readmes_count": 3,
  "errors": []
}
```

Esempio - deep FAILED:
```json
{
  "mode": "deep",
  "status": "failed",
  "errors": [
    "Vision hard check failed; verifica secrets/permessi: ...",
    "Drive hard check fallito; verifica secrets/permessi/drive (...)"
  ],
  "checks": [
    "vision_hardcheck",
    "drive_hardcheck",
    "golden_pdf"
  ],
  "external_checks": {
    "vision_hardcheck": {
      "ok": false,
      "details": "Vision run failed | sentinel=..."
    },
    "drive_hardcheck": {
      "ok": false,
      "details": "Drive exception: ..."
    }
  },
  "golden_pdf": {
    "path": ".../raw/golden_dummy.pdf",
    "sha256": "abc123",
    "bytes": 1234
  }
}
```

---

## Pattern da evitare
- Hardcode del modello LLM nei servizi (`MODEL = "gpt-..."`): usa `get_vision_model()`.
- `print` o `basicConfig` per logging.
- Letture/scritture senza path-safety o writer atomici.
- Side-effect a import-time (I/O, letture env, configurazioni globali).

---

## Typing coverage & debt
`mypy --config-file mypy.ini src/pipeline src/semantic src/ui` deve essere pulito in CI (`strict` per namespace). I blocchi ancora esclusi dalla copertura formale sono:

- `src/adapters/**`  integrazioni esterne e client API da rifinire con TypedDict/Protocol.
- `tools/**`  script CLI con forte uso di `googleapiclient`; serve incapsulare le chiamate e aggiungere annotazioni pubbliche.
- `tools/**`  tooling operativo legacy; va consolidato in moduli riusabili prima della tipizzazione.

Checklist per le PR che riducono il debito:
1. Isolare un sotto-scope (max ~30 righe modificate) e rendere le funzioni import-safe.
2. Introdurre `dataclass`/`TypedDict`/`Protocol` al posto di `dict[str, Any]`/`Any` nelle API condivise.
3. Eliminare i cast ridondanti e aggiungere annotazioni alle entrypoint pubbliche.
4. Eseguire `mypy --config-file mypy.ini src/<scope>` e aggiornare `mypy.ini` solo quando il comando e pulito.
5. Documentare nel changelog interno la sezione migrata (link alla PR e note di compatibilita).

---

## Esempi rapidi (UI/Servizi)
```python
# Lettura modello e chiamata Responses API
from ui.config_store import get_vision_model
from ai.client_factory import make_openai_client

MODEL = get_vision_model()
client = make_openai_client()
resp = client.responses.create(
    model=MODEL,
    input=[
        {"role": "system", "content": "Sei un assistente..."},
        {"role": "user", "content": "<prompt>"},
    ],
)
text = resp.output_text
```

```python
# Logging evento UI + scrittura YAML sicura
from pipeline.logging_utils import get_structured_logger
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve

log = get_structured_logger("ui.manage.tags")
yaml_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml")
safe_write_text(yaml_path, yaml_content, encoding="utf-8", atomic=True)
log.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
```

---

## Contributi
- PR piccole, commit atomici, messaggi chiari (imperativo al presente).
- Ogni modifica di comportamento va coperta da test.
