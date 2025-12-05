# Developer Guide  v1.0 Beta

Guida per sviluppare e manutenere **Timmy KB** in modo coerente e sicuro. Questa versione e la base iniziale della documentazione tecnica: niente riferimenti a legacy o migrazioni passate.
Per un percorso rapido step-by-step vedi anche [Developer Quickstart](developer_quickstart.md).

---

## Obiettivi
- **SSoT (Single Source of Truth)** per configurazioni, dipendenze e utility condivise.
- **Logging strutturato centralizzato**, redazione automatica dei segreti, handler idempotenti.
- **Path-safety** e **scritture atomiche** per ogni I/O nel workspace cliente.
- **UI import-safe** (nessun sideeffect a import-time).
- **Parita di firma** tra wrapper/facade UI e backend `pipeline.*`/`semantic.*`.
- **Riproducibilita ambienti** tramite pin gestiti con `pip-tools` (requirements/constraints).

---

## Architettura in breve
- **Pipeline** (`pipeline.*`): funzioni SSoT per I/O, path-safety, logging, semantica e orchestrazione.
- **UI/Service Layer** (`src/ui/*`): presenta funzioni e schermate Streamlit, delega alla pipeline senza cambiare semantica.
- **Semantic** (`semantic.*`): conversione PDFMarkdown, arricchimento frontmatter, generazione `SUMMARY.md`/`README.md`.
- **Workspace cliente**: `output/timmy-kb-<slug>/` con sottocartelle `raw/`, `book/`, `semantic/`, `config/`, `logs/`.
- **DB KB per slug**: `semantic/kb.sqlite` vive nel workspace cliente; fallback legacy sul DB globale `data/kb.sqlite` solo per tool/test espliciti.

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
- Il flusso **Assistant** usa l'ID letto da l'env il cui nome Ã¨ in `ai.vision.assistant_id_env`.
- Accesso runtime **solo** tramite `pipeline.settings.Settings` / `ClientContext.settings` (UI inclusa); niente letture YAML manuali.
- Config cliente: API unica `pipeline.config_utils.load_client_settings(context)` â†’ `context.settings` â†’ `.as_dict()` per le UI/CLI.

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

- `GITBOOK_TOKEN` e `GITBOOK_SPACE_ID` servono per pubblicare automaticamente il contenuto `book/` su GitBook. Esporta questi valori in `.env` o nelle secret variables dei runner CI (do not commit them). Il token deve avere permessi di scrittura sullo spazio indicato.
- Use `tools/gitbook_publish_smoke.py --slug <slug> --dry-run` per validare localmente la summary e i secrets prima di eseguire `py src/onboarding_full.py --slug <slug> --non-interactive`, che ora invia lo ZIP con metadata `layout_summary`.

---

## Logging centralizzato
Usa sempre il logger strutturato della pipeline; vietati `print`, `logging.basicConfig` e `logging.getLogger(...)` nei moduli.

```python
from pipeline.logging_utils import get_structured_logger

log = get_structured_logger(__name__, run_id=None, context={"slug": "acme"})
log.info("ui.preview.open", extra={"slug": "acme", "page": "preview"})
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
- Deriva i path dal workspace cliente (mai costruire manualmente stringhe tipo `output/timmy-kb-<slug>`).
- Prima di leggere/scrivere, **risolvi** e **valida** il path con gli helper della pipeline.
- Usa writer atomici per evitare file parziali/corruzione.

```python
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.file_utils import safe_write_text

yaml_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml")
safe_write_text(yaml_path, content, encoding="utf-8", atomic=True, fsync=False)
```

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
    ui = importlib.import_module('src.ui.utils.core')
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
pre-commit install --hook-type pre-commit --hook-type pre-push
make qa-safe     # isort/black/ruff/mypy (se presenti)
make ci-safe     # qa-safe + pytest
```

---

## Test: piramide e casi minimi
- **Unit**  **contract/middle**  **smoke E2E** (dataset dummy; nessuna rete).
- Casi minimi obbligatori:
  - Slug invalidi (devono essere scartati/validati).
  - Traversal via symlink in `raw/` (gli helper non devono attraversare).
  - Parita di firma wrapper UI  backend e passthrough dei parametri.
  - Invarianti su `book/` (presenza `README.md`/`SUMMARY.md` dopo onboarding).

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
- `src/tools/**`  script CLI con forte uso di `googleapiclient`; serve incapsulare le chiamate e aggiungere annotazioni pubbliche.
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
