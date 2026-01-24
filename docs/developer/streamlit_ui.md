# Streamlit UI  linee guida (dettagliate)

Queste linee guida descrivono il modulo Streamlit come parte dell'ambiente Timmy-KB: il tool implementa un'interfaccia operativa, ma rimane sotto il controllo umano e osserva l'envelope epistemico senza assumere autonomie decisionali.

*Allineato alle regole di progetto (vedi *[***coding\_rule.md***](./developer/coding_rule.md)*)*.

---

## Perche queste regole (in breve)

- **Sicurezza**: impedire path traversal/symlink malevoli e scritture non atomiche.
- **Osservabilita**: avere log strutturati e stabili, senza PII, per investigazioni/metriche.
- **Testabilita**: far girare i test senza il runtime Streamlit reale (stub), anche su Windows.
- **Coerenza**: un'unica fonte di verita per stati, query string, e gating funzionali.

---

## Indice

- [Prerequisiti (UI Onboarding)](#prerequisiti-ui-onboarding)
- [Routing e Deep-Linking (fonte unica)](#routing-e-deep-linking-fonte-unica)
- [Query string & slug](#query-string--slug)
  - [Perche ](#perche-stquery_params)[`st.query_params`](#perche-stquery_params)
  - [API consigliata: ](#api-consigliata-uiutils-route_state--uiutils-slug)[`ui.utils.route_state` + `ui.utils.slug`](#api-consigliata-uiutils-route_state--uiutils-slug)
  - [Esempi e anti-pattern](#esempi-e-anti-pattern)
- [New pages](#new-pages)
- [Path-safety (lettura/scrittura)](#path-safety-letturascrittura)
  - [Flusso consigliato](#flusso-consigliato)
  - [Workspace root (REPO_ROOT_DIR / WORKSPACE_ROOT_DIR)](#workspace-root-repo_root_dir--workspace_root_dir)
  - [Esempi pratici](#esempi-pratici)
- [Scan PDF sicuro (DRY)](#scan-pdf-sicuro-dry)
- [Eventi di log strutturati](#eventi-di-log-strutturati)
  - [Tassonomia logging](#tassonomia-logging)
  - [Naming & payload](#naming--payload)
  - [Esempi: pagina Manage](#esempi-pagina-manage)
  - [Test con ](#test-con-caplog)[`caplog`](#test-con-caplog)
- [Gating e SSoT di stato](#gating-e-ssot-di-stato)
- [Compatibilita con gli stub di Streamlit nei test](#compatibilita-con-gli-stub-di-streamlit-nei-test)
- [Checklist UI page](#checklist-ui-page)
- [FAQ](#faq)
- [Anti-pattern da evitare](#anti-pattern-da-evitare)

---

## Prerequisiti (UI Onboarding)

- **Streamlit  1.50.0**  il router nativo (`st.Page`, `st.navigation`) e obbligatorio.
- Deep-linking via `st.query_params` e supportato, ma l'accesso deve passare dagli helper centralizzati (vedi sotto).

---

## Routing e Deep-Linking (fonte unica)

Il routing client-side deve usare le facade in `src/ui/utils/route_state.py`, che mantengono sincronizzati query string e stato interno.

```python
from ui.utils.route_state import get_tab, set_tab, clear_tab, get_slug_from_qp

current_tab = get_tab("home")  # default se ?tab assente
slug = get_slug_from_qp()      # slug opzionale

set_tab("manage")              # aggiorna query params + rerun ordinato
clear_tab()                    # pulisce lo stato
```

Se serve il deep-link pieno, invoca `set_tab("home")` appena la pagina viene idratata.

Esempio router completo nell'entrypoint:

```python
import streamlit as st
from ui.pages.registry import build_pages

pages = build_pages()
navigation = st.navigation(pages, position="top")
navigation.run()
```

---

## Query string & slug

`st.query_params` resta l'SSoT lato client, ma l'accesso passa da `ui.utils.route_state` (tab + letture slug) e da `ui.utils.slug` (setter/getter ad alto livello). Quando serve garantire la presenza dello slug e rendere coerente l'UI (sidebar, breadcrumbs, titoli), usa i facade come `render_chrome_then_require`.

### Perche `st.query_params`

- Evita parsing manuale degli URL.
- Funziona come dizionario reattivo: gli update triggerano un **rerun** della pagina.
- E coperto dai nostri stub di test.

### API consigliata: `ui.utils.route_state` + `ui.utils.slug`

```python
from ui.utils.route_state import get_tab, set_tab, clear_tab, get_slug_from_qp
from ui.utils.slug import get_active_slug, set_active_slug, clear_active_slug

# Legge stato/query params
tab = get_tab()
slug = get_slug_from_qp() or get_active_slug()

# Aggiorna tab/slug sincronizzando query params e chrome
set_tab("manage")
set_active_slug("dummy-srl")
```

Oppure, quando la pagina **richiede** lo slug:

```python
from ui.chrome import render_chrome_then_require

# Se allow_without_slug=False (default), la pagina blocca e guida l'utente
slug = render_chrome_then_require()
```

### Esempi e anti-pattern

**OK**

```python
slug = get_slug_from_qp() or get_active_slug() or "dummy-srl"
set_tab("manage")                  # se serve cambiare tab
```

**EVITARE**

```python
#  Non leggere/scrivere direttamente dalla stringa dellURL
#  Non conservare lo slug in variabili globali non sincronizzate con query params
```

---

## New pages

Pattern unificato per aggiungere pagine Streamlit tramite `ui.pages.registry`.

- **Admin pages**
  - Operano a livello globale: chiamare `header(None)` e `sidebar(None)` cosi l'interfaccia ignora lo slug.
  - Non forzano la selezione del cliente; i testi devono ricordare che lavorano sull'intero workspace.
  - Registrazione nel gruppo `Admin` in `registry.py` con `url_path` opzionale (`None` per pagine interne come `logs_panel`).
- **Tools pages**
  - Agiscono su un cliente: usare `render_chrome_then_require()` per ottenere/forzare lo slug.
  - In assenza di slug mostrano la CTA guidata gia gestita da `render_chrome_then_require`.
  - Registrazione nel gruppo `Tools`; mantenere messaging slug-centrico (es. 'Workspace: slug').

Checklist minima per una pagina nuova:

1. Copiare uno scheletro esistente (`home.py` per Admin, `diagnostics.py` per Tools) dentro `src/ui/pages/`.
2. Richiamare header/sidebar coerenti con il tipo di pagina (Admin -> `None`, Tools -> slug richiesto).
3. Aggiornare `ui/navigation_spec.py` (coppia `PagePaths` + `NAVIGATION_GROUPS`) cosi da riflettere titolo/gruppo/url-path della nuova pagina; rigenerare gli snapshot con `python tools/ci_dump_nav.py` se cambiano i gruppi.
4. Aggiungere/aggiornare i test UI (`tests/ui/...`) sfruttando gli stub Streamlit.
5. Validare con `python tools/test_runner.py full` per riallineare la suite e i contratti di navigazione.

---

## path-safety (lettura/scrittura)

### Flusso consigliato

1. Risolvi `WorkspaceLayout` a partire dallo slug con `ui.utils.workspace.get_ui_workspace_layout(slug, require_env=False)` (o `WorkspaceLayout.from_<...>` nei contesti CLI).
2. Usa i campi `layout.raw_dir`, `layout.normalized_dir`, `layout.semantic_dir`, `layout.tags_db` e `layout.vision_pdf` per qualsiasi accesso ai file.
3. Valida tramite `pipeline.path_utils.ensure_within_and_resolve` e scrivi con helper atomici (`safe_write_text`, `safe_write_bytes`, ecc.).

> Gli helper legacy `resolve_raw_dir` e `workspace_root` seguono ancora la firma compatibile, ma non devono essere usati nei nuovi modules che già hanno il layout; preferisci sempre `layout.raw_dir`/`layout.normalized_dir`/`layout.repo_root_dir` (root canonica).

### Workspace root (REPO_ROOT_DIR / WORKSPACE_ROOT_DIR)

- `REPO_ROOT_DIR` ha precedenza quando impostato: se contiene `.git` o `pyproject.toml` viene trattato come root repo e deriva `output/timmy-kb-<slug>`, altrimenti viene usato come workspace diretta (legacy/test).
- `WORKSPACE_ROOT_DIR` viene usato quando `REPO_ROOT_DIR` manca; accetta anche il placeholder `<slug>` e viene risolto in un path assoluto, utile per puntare a una workspace cliente specifica.
- Se entrambe sono assenti, la pipeline richiede un workspace root canonico via API.
- Su Windows e Linux usare path assoluti coerenti (niente drive letter nei path relativi).

### Esempi pratici

**Caricare/modificare** `semantic/tags_reviewed.yaml` con layout-first:

```python
from ui.utils.workspace import get_ui_workspace_layout
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.utils.core import safe_write_text
import yaml

def _get_layout(slug: str):
    return get_ui_workspace_layout(slug, require_env=False)

def load_tags_yaml(slug: str) -> str:
    layout = _get_layout(slug)
    yaml_path = ensure_within_and_resolve(layout.semantic_dir, layout.semantic_dir / "tags_reviewed.yaml")
    try:
        return read_text_safe(yaml_path.parent, yaml_path, encoding="utf-8")
    except Exception:
        return "version: 2\nkeep_only_listed: true\ntags: []\n"

def save_tags_yaml(slug: str, text: str) -> None:
    yaml.safe_load(text)
    layout = _get_layout(slug)
    yaml_path = ensure_within_and_resolve(layout.semantic_dir, layout.semantic_dir / "tags_reviewed.yaml")
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(yaml_path, text, encoding="utf-8", atomic=True)
```

Per trovare il DB dei tag o il VisionStatement.pdf basta usare `layout.tags_db` o `layout.vision_pdf`, senza ricostruirli manualmente da `layout.semantic_dir` o `layout.config_path`.

**Perche atomico?** Minimizza corruzioni/condizioni di gara: si scrive su un file temporaneo e poi si fa un rename.

---

### Registry clienti (CLIENTS_DB_*)

- `CLIENTS_DB_PATH` (alias) o la coppia `CLIENTS_DB_DIR`/`CLIENTS_DB_FILE` accettano **solo** percorsi relativi al workspace; niente drive letter o path assoluti.
- Il file deve vivere sotto `clients_db/`; eventuali sottocartelle sono consentite (`clients_db/archive/clients.yaml`).
- Gli helper della UI rifiutano componenti `..`: se serve un percorso alternativo, monta un workspace dedicato e aggiorna `REPO_ROOT_DIR`.
- Lo smoke dummy registra un entry `dummy` con flag `dummy: true` e un campo opzionale `created_at`; la UI deve ignorare eventuali campi extra (es. `health` nel payload CLI) mantenendo compatibilita forward.

## Scan PDF sicuro (DRY)

Per contare/iterare i PDF **non** usare `Path.rglob`/`os.walk`. Usa sempre l'utility condivisa `iter_safe_pdfs` che applica path-safety forte, ignora i symlink e restituisce path canonicalizzati in ordine deterministico.

```python
from pipeline.path_utils import iter_safe_pdfs

for pdf_path in iter_safe_pdfs(raw_dir):
    ...
```

Se sei in UI, `ui.utils.workspace.iter_pdfs_safe` e un wrapper che inoltra alla stessa utility. In questo modo tutte le sezioni della pipeline (UI, semantic, tool CLI) condividono lo stesso comportamento e i test coprono gia i corner case (symlink, traversal, Windows).
Per altri casi d'uso (alberi completi, Markdown, ecc.) usa `pipeline.path_utils.iter_safe_paths(...)`, che replica le stesse guardie per directory e file generici. Evita nuove implementazioni basate su `os.walk`/`Path.rglob`.

---

## Ingestion Vocabolario (YAML -> DB)

```mermaid
flowchart TD
    A[Authoring umano\nsemantic/tags_reviewed.yaml] --> B[Loader YAML\n(validazione + normalizzazione)]
    B --> C[Derivazione percorso DB\n_derive_tags_db_path(...)]
    C --> D[Ensure schema v2\nensure_schema_v2(...)]
    D --> E[Upsert termini canonici\nterms(canonical)]
    E --> F[Upsert cartelle (percorso)\nfolders(path)]
    F --> G[Upsert relazioni\nfolder_terms(folder_id, term_id, weight)]
    G --> H[(SQLite tags.db)]
    H --> I[Runtime UI/Pipeline\n(normalize/enrich/index)]
```

```mermaid
erDiagram
    TERMS {
        INTEGER id PK
        TEXT    canonical  "termine canonico (lowercase, unico)"
    }

    FOLDERS {
        INTEGER id PK
        TEXT    path       "percorso relativo (es. normalized/..., book/...)"
    }

    FOLDER_TERMS {
        INTEGER folder_id FK
        INTEGER term_id   FK
        REAL    weight    "se disponibile (default=1.0)"
    }

    TERMS ||--o{ FOLDER_TERMS : "tagga"
    FOLDERS ||--o{ FOLDER_TERMS : "contiene"
```

| Campo YAML         | Normalizzazione                | Destinazione DB             | Note                                   |
|--------------------|--------------------------------|-----------------------------|----------------------------------------|
| `tags[].canonical` | lowercase, trim, deduplicate   | `terms.canonical`           | Unico; merge se duplicato              |
| `tags[].aliases[]` | lowercase, trim                | (merge in memoria)          | Nessuna tabella `aliases` attualmente |
| `tags[].folders[]` | percorso relativo normalizzato | `folders.path`              | Path relativi (normalized/book/semantic)     |
| folder -> tag link | -                              | `folder_terms(..., weight)` | `weight` facoltativo (default 1.0)    |

```python
# Pseudocode: ingest YAML -> DB (layer storage.tags_store)
def import_tags_yaml_to_db(semantic_dir: Path, yaml_path: Path, logger):
    db_path = _derive_tags_db_path(yaml_path)
    _ensure_tags_schema_v2(str(db_path))

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    terms: dict[str, int] = {}
    folders: dict[str, int] = {}
    links: list[tuple[int, int, float]] = []

    for entry in raw.get("tags", []):
        canonical = norm(entry.get("canonical"))
        if not canonical:
            continue
        tid = upsert_term(db_path, canonical)
        terms[canonical] = tid

        for folder_path in map(norm_path, entry.get("folders") or []):
            if not folder_path:
                continue
            fid = upsert_folder(db_path, folder_path)
            folders[folder_path] = fid
            links.append((fid, tid, 1.0))

    upsert_folder_terms(db_path, links)
    logger.info(
        "semantic.tags_yaml.imported",
        extra={"db": str(db_path), "terms": len(terms), "links": len(links)},
    )
```

> Il loader YAML deve validare lo schema, normalizzare canonical/alias/path e gestire duplicati. L'upsert e idempotente (nessun wipe massivo del DB).

---

## Eventi di log strutturati

### Tassonomia logging

- Vision: `semantic.vision.*` (es. `semantic.vision.create_thread`, `semantic.vision.run_failed`, `semantic.vision.completed`)
- Conversione/Book: `semantic.convert.*`, `semantic.summary.*`, `semantic.readme.*`, `semantic.book.*`
- Indicizzazione: `semantic.index.*`

### Naming & payload

- Schema: `ui.<pagina>.<sottoarea>.<azione>` (es.: `ui.manage.tags.save`).
- **Niente PII** o contenuto file; payload **minimale** (`slug`, path relativo/basename, messaggio errore redatto).
- Usa **solo** `get_structured_logger("ui.<pagina>")`; i filtri globali gestiscono la redazione.

### Esempi: pagina Manage

```python
import logging
from pipeline.logging_utils import get_structured_logger
LOGGER = get_structured_logger("ui.manage")

# Apertura editor
LOGGER.info("ui.manage.tags.open", extra={"slug": slug})

# Validazione YAML
try:
    yaml.safe_load(content)
    LOGGER.info("ui.manage.tags.yaml.valid", extra={"slug": slug})
except Exception as exc:
    LOGGER.warning("ui.manage.tags.yaml.invalid", extra={"slug": slug, "error": str(exc)})
    ...

# Salvataggio (ok/errore)
LOGGER.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
LOGGER.warning("ui.manage.tags.save.error", extra={"slug": slug, "error": str(exc)})
```

### Test con `caplog`

```python
def test_emette_eventi_tags(caplog, monkeypatch):
    import ui.pages.manage as manage

    caplog.set_level("INFO")
    slug = "acme"

    # Monkeypatch writer per evitare I/O reale
    monkeypatch.setattr(manage, "safe_write_text", lambda *a, **k: None)

    # Simula azioni utente (p.es. click su Salva + contenuto valido)
    ...

    # Assert sugli eventi
    assert any("ui.manage.tags.open" in r.message for r in caplog.records)
    assert any("ui.manage.tags.save" in r.message for r in caplog.records)
```

---

## Gating e SSoT di stato

La semantica è disponibile da stato 'pronto' in poi e richiede Markdown presenti in `normalized/`.

1. Calcola i gate con `ui.gating.compute_gates(os.environ)`; combina la disponibilita runtime dei servizi (`ui.services.*`) con gli override da variabili di ambiente:
    - `DRIVE=0` disabilita i flussi Drive (cartelle, cleanup, download).
    - `VISION=0` disabilita il provisioning Vision (estrazione PDF, tool assistito).
    - `TAGS=0` disabilita il tagging e le pagine Semantica e Preview Docker.
    - Qualsiasi altro valore oppure l'assenza della variabile mantiene il default calcolato dal runtime.
2. Trasforma i gate in navigation ready con `ui.gating.visible_page_specs(gates)` e passa l'elenco filtrato al router:

```python
from ui.gating import compute_gates, visible_page_specs
from ui.utils.stubs import get_streamlit

st = get_streamlit()
gates = compute_gates()
pages = {
    group: [st.Page(spec.path, title=spec.title, url_path=spec.url_path or None)]
    for group, specs in visible_page_specs(gates).items()
}
st.navigation(pages)
```

**Perche**: il router vede solo le pagine abilitate, quindi nessun tab inceppa il flusso quando i servizi sono assenti (localmente o in produzione controllata).
In aggiunta al gate `TAGS`, la pagina *Semantica* viene mostrata solo quando lo slug attivo ha Markdown validi in `normalized/` (`ui.utils.workspace.has_normalized_markdown`). Analogamente la pagina *Preview* viene resa visibile solo se `normalized/` è pronto e lo stato cliente appartiene a `SEMANTIC_READY_STATES`; in caso contrario il router emette `ui.gating.sem_hidden`/`ui.gating.preview_hidden` per telemetria.

### Modalita stub e SSoT semantica

Per le pagine semantiche, oltre ai gate controlliamo lo stato del cliente:

```python
from ui.constants import SEMANTIC_ENTRY_STATES, SEMANTIC_READY_STATES
from ui.pages import semantics as sem

try:
    sem._require_semantic_gating(slug)
except RuntimeError as exc:
    st.info(SEMANTIC_GATING_MESSAGE)
    st.caption(str(exc))
    st.stop()

- Il messaggio `SEMANTIC_GATING_MESSAGE` viene riciclato anche nel testo doc: La semantica è disponibile da stato 'pronto' in poi e richiede Markdown presenti in `normalized/`. Cosi lo snippet rimane allineato alla stringa effettiva (test: `tests/ui/test_semantics_state.py::test_semantics_message_string_matches_docs`).
```

**Nota**: il test di contratto (`pytest -m "contract"`) fotografa le pagine visibili per combinazioni di gate e fallisce se una PR introduce regressioni.

> Per mantenere lo stesso gating anche nelle esecuzioni *headless* (stub di Streamlit, runner CLI, test unitari) la UI centralizza il controllo in `_require_semantic_gating(slug)`. La funzione chiama `normalized_ready`/`get_state`, solleva `RuntimeError` se `normalized/` non è presente o lo stato non è in `SEMANTIC_ENTRY_STATES`, e viene invocata sia appena la pagina viene caricata sia prima dell'avvio di `_run_convert/_run_enrich/_run_summary`. In questo modo anche gli automation test falliscono immediatamente con lo stesso messaggio visibile alla UI e nessun branch puo bypassare il gate.

### Env preview stub e logging

Il percorso "Preview Docker" supporta una modalita stub pensata per CI ed e2e:

- `PREVIEW_MODE=stub` forza l'uso della pipeline fake senza container reali.
- `PREVIEW_LOG_DIR=/percorso/custom` definisce la cartella dove scrivere i log stub (deve esistere ed essere scrivibile).
- Ogni path viene normalizzato con `ensure_within_and_resolve` e scritto in modo atomico tramite `safe_write_text`.
- Eventi strutturati emessi: `ui.preview.stub_started`, `ui.preview.stub_stopped`, `ui.preview.start_failed`, `ui.preview.stop_failed`.

Quando abiliti lo stub ricorda di puntare `CLIENTS_DB_PATH` e altre risorse persistenti a directory isolate (`tmp_path` nelle fixture), cosi gli end-to-end non toccano workspace reali.

## Compatibilita con gli stub di Streamlit nei test

I test girano con uno **stub** di Streamlit (assenza del runtime reale). Per evitare rotture:

- Tipizza sempre `st` come `StreamlitLike` (`from ui.types import StreamlitLike`); negli unit test usa `StreamlitStubAdapter(StreamlitStub())` da `tests/ui/streamlit_like_adapter.py` per rispettare il contratto.
- Avvolgi le chiamate facoltative con `getattr(st, "api", None)` e verifica che siano **callable**.
- Fallback per layout:
- Se devi azzerare lo stato condiviso tra test, chiama `ui.utils.stubs.reset_streamlit_stub()` nelle fixture (`autouse=True` consigliato).

```python
_markdown = getattr(st, "markdown", None)
if callable(_markdown):
    _markdown("")

# Columns resilienti
make_cols = getattr(st, "columns", None)
if callable(make_cols):
    try:
        c1, c2, c3 = make_cols([1, 1, 1])
    except Exception:
        cols = list(make_cols(3)) if callable(make_cols) else []
        while len(cols) < 3:
            cols.append(cols[-1] if cols else st)
        c1, c2, c3 = cols[:3]
else:
    c1 = c2 = c3 = st

# NO with c1: ... se lo stub non supporta il context manager
# Preferisci: c1.button(...), c2.button(...)
```

- Evita pattern che forzano `with col:` sugli stub: alcuni colonnati mock non implementano il context manager.
- Per le pagine piu recenti (Onboarding, Semantica, Admin) l'UI è incapsulata in `main()` e gli import non generano side-effect; mantieni questo pattern per i nuovi moduli.

---

### Tema ufficiale + Enhancement CSS (progressive enhancement)

Il **tema ufficiale** vive in `.streamlit/config.toml` ed e la fonte unica del brand (palette, font, base light/dark). Questo garantisce coerenza visiva anche qualora l'iniezione HTML venga bloccata o filtrata. Gli **enhancement CSS** (iniettati una sola volta via `st.html`) servono solo per micro-affinamenti non esposti dalle opzioni native: radius **gentili**, micro-spaziature, focus ring accessibile, piccoli fix di rendering. In pratica: colori e tipografia nel `config.toml`; dettagli tattili e a11y nell'enhancement. Manteniamo gli enhancement **idempotenti**, compatibili con light/dark (evitare override cromatici aggressivi) e confinati in un `<style id="nexty-theme-enhancements">` per tracciabilita e rollback. Criterio di accettazione: con gli enhancement disattivati il brand resta intatto; riattivandoli si percepisce solo un miglioramento della qualita interattiva senza variazioni di palette o regressioni di leggibilita.

- Vedi `.streamlit/config.toml` per la configurazione completa: per passare a base scura mantenendo la palette esistente e sufficiente impostare `base = "dark"` e riavviare la UI.

---

## Checklist UI page

Prima di aprire una PR:

**Stato & routing**

- Usa `st.Page`/`st.navigation` e niente router legacy.
- Se la pagina richiede slug: `render_chrome_then_require()` / `require_active_slug()`.
- Navigazione interna con `st.page_link`; usa `st.switch_page(PagePaths.X)` solo dopo side-effects (salvataggi, reset) dove serve rerun controllato.

**File I/O**

- Path-safety con `ensure_within_and_resolve`, I/O atomico con `safe_write_text`.
- Niente `Path.rglob` sui workspace: usa `iter_pdfs_safe`/`count_pdfs_safe`.

**Osservabilita**

- Logger `ui.<pagina>` e eventi minimali senza PII (vedi esempi Manage).

**UX & stub-compat**

- Feedback con `status_guard` o `st.status` (no sleep/progress finti).
- Modali: usa `st.dialog` se disponibile, altrimenti degrada inline con un semplice render del corpo.
 - Evita `with col:` se lo stub non lo supporta; usa gli helper centralizzati:
   `from ui.utils.ui_controls import columns3, column_button, button`.

---

### Registry dei path UI (SSoT)
Per evitare divergenze tra `onboarding_ui.py` (router) e i link nelle pagine, i path sono definiti una sola volta in `ui/navigation_spec.PagePaths` (ri-esportato da `ui.pages.registry`).
Usa:
- `from ui.pages.registry import PagePaths` per link diretti (`st.page_link(PagePaths.NEW_CLIENT, ...)`).
- `from ui.pages.registry import build_pages` nell'entrypoint per generare il `pages` dict per `st.navigation(...)`.

La navigazione programmativa deve passare da `st.switch_page(PagePaths.X)`; preferisci il link dichiarativo (`st.page_link(...)`) quando non hai side-effect da completare prima del rerun.

---


## FAQ

**D: Posso usare **`Path.write_text`** per scrivere file?**\
R: No. Usa **sempre** `safe_write_text(..., atomic=True)` per garantire atomicita e logging coerente.

**D: Perche non posso usare **`Path.rglob`**?**\
R: Non e path-safe e puo seguire symlink non desiderati. Usa `iter_pdfs_safe`/`count_pdfs_safe`.

**D: Dove metto i log?**\
R: Logger strutturato di pagina: `from pipeline.logging_utils import get_structured_logger`  `LOGGER = get_structured_logger('ui.manage')`. Eventi `ui.manage.*`.

**D: Come gestisco la validazione YAML?**\
R: Valida **prima** di scrivere (`yaml.safe_load`) e, in caso di errore, emetti `ui.<pagina>.<area>.yaml.invalid` senza persist.

---

## Anti-pattern da evitare

-  `Path(...).rglob('*.pdf')`, `os.walk(...)` sul workspace  **usa** `iter_pdfs_safe` / `count_pdfs_safe`.
-  Scritture non atomiche (`open(..., 'w')`)  **usa** `safe_write_text(...)`.
-  Path costruiti a mano senza guardrail  **usa** `ensure_within_and_resolve(...)`.
-  Dati sensibili nei log (contenuti, token, path assoluti di sistema).
-  Dipendenze dirette da API Streamlit non stubbate senza `getattr(...)`/fallback.

---

### Note finali

- Questo documento e SSoT per la UI Streamlit e si affianca a [coding\_rule.md](./developer/coding_rule.md).
- Gli esempi sono tratti da implementazioni reali nelle pagine **Manage** e **Semantics** e risultano eseguibili nel progetto.
