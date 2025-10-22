# Timmy-KB - Coding Rules (v2.2.0)
<!-- cSpell:ignore Novita -->

Linee guida per contribuire al codice in modo coerente, sicuro e manutenibile.

> Doppio approccio: puoi lavorare da terminale (orchestratori in sequenza) oppure tramite interfaccia (Streamlit).
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Principi
- **SSoT (Single Source of Truth)**: riusa utility già presenti; evita duplicazioni.
- **Idempotenza**: ogni step deve poter essere rieseguito senza effetti collaterali.
- **Path-safety**: nessuna read/write/copy/rm senza passare da utility di sicurezza.
- **Slug hygiene**: validazione centralizzata; nessuna persistenza UI senza `validate_slug`.
- **Fail-fast & messaggi chiari**: errori espliciti e log azionabili.
- **Compatibilità cross-platform**: Windows/Linux (path, encoding, newline).
- **Contratti condivisi**: per funzioni che richiedono solo `base_dir/raw_dir/md_dir/slug`, usa `semantic.types.ClientContextProtocol` invece di protocolli locali duplicati.
- **No side-effects a import-time**: nessun I/O o lettura di env vars a livello di modulo.
- **Adozione dipendenze**: prima di aggiungere una libreria, valuta sicurezza, licenza, maturità, impatto su CI/CD e alternative già adottate.

---

## Interfaccia Streamlit
- Target: **Streamlit 1.50.0**.

| Area/Componente            | Deprecato                                                 | Usa invece                                      | Note sintetiche |
|---------------------------|-----------------------------------------------------------|-------------------------------------------------|-----------------|
| Query string              | `st.experimental_get_query_params` / `st.experimental_set_query_params` | `st.query_params`                               | API dict-like: `clear()`, `from_dict()`, `get_all()`, `to_dict()` |
| Rerun                     | `st.experimental_rerun`                                   | `st.rerun`                                      | Rerun esplicito, niente `experimental` |
| Caching (generale)        | `st.cache`                                                | `@st.cache_data` / `@st.cache_resource`         | **Data** = funzioni pure; **Resource** = client/connessioni |
| Data editor               | `st.experimental_data_editor`                             | `st.data_editor`                                | Stato: da `edited_cells` → `edited_rows` |
| Navigazione               | Directory `pages/`                                        | `st.navigation` + `st.Page`                     | Router unico; `pages/` ignorata se usi `st.navigation` |
| Immagini/Tabelle/Buttons  | `use_container_width`                                     | `width="content|stretch|<int>"`                | Preferisci `width="stretch"` |
| Matplotlib (`st.pyplot`)  | Figura globale implicita                                  | `fig=` esplicito + `width/height`               | Passa **sempre** `fig` |

Vedi dettagli completi in [streamlit_ui.md](streamlit_ui.md).

---

## **UI Path-Safety & Slug Hygiene** (nuova sezione)
**Obbligatorio**: qualunque funzionalità UI che legga/scriva nel workspace cliente deve:

1. **Sanificare lo slug** (query/session/persistenza):
```py
from ui.utils.query_params import get_slug, set_slug
# get_slug() legge e valida; ritorna None se invalido
slug = get_slug()
```
Oppure, se arriva da input utente:
```py
from pipeline.context import validate_slug
slug = value.strip().lower()
validate_slug(slug)  # alza ConfigError su slug non valido
```

2. **Derivare i path dal workspace sicuro**:
```py
from ui.utils.workspace import resolve_raw_dir
from pipeline.path_utils import ensure_within_and_resolve

raw_dir = resolve_raw_dir(slug)                  # valida slug + path safety
base_dir = raw_dir.parent                        # workspace root
yaml_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml")
```
> Vietato costruire `output/timmy-kb-<slug>` a mano.

3. **Scansionare i file in modo sicuro** (no `Path.rglob` su input non affidabili):
```py
from ui.utils.workspace import iter_pdfs_safe, count_pdfs_safe

for pdf in iter_pdfs_safe(raw_dir):
    ...
count = count_pdfs_safe(raw_dir)
```
Gli helper eseguono `os.walk(..., followlinks=False)` e validano ogni path con `ensure_within_and_resolve`.

4. **Persistenza UI**: usare writer sicuri e atomici:
```py
from ui.utils.core import safe_write_text
safe_write_text(yaml_path, content, encoding="utf-8", atomic=True)
```

5. **Merge di configurazioni**: quando combini template repo e configurazioni cliente, usa l'helper condiviso:
```py
from ui.utils.merge import deep_merge_dict
merged = deep_merge_dict(template_cfg, client_cfg)
```
Garantisce merge ricorsivo senza mutare l'input e previene la perdita di chiavi annidate.

---

## Struttura & naming
- Slug e nomi cartelle: normalizza con `to_kebab()` dove previsto; valida con `validate_slug`.
- RAW/BOOK/SEMANTIC: non cambiare convenzioni senza aggiornare orchestratori e documentazione.
- File generati: mantieni posizionamento in `output/timmy-kb-<slug>/...` **derivando i path via helper** (vedi sezione sopra).

---

## Python style
- Tipizzazione obbligatoria sui moduli core: annota parametri e ritorni. Usa `Optional[...]` in modo esplicito.
- Evita `Any` e i wild import; mantieni import espliciti e ordinati.
- Funzioni corte, una responsabilità; preferisci pure functions dove possibile.
- No side-effects in import (es. no I/O top-level).
- Estrai helper privati (SRP) se una funzione supera ~40–50 righe o mescola traversal/rendering/I/O.
- Aggiorna le docstring delle funzioni core (stile Google o Sphinx).

---

## Qualità prima dei test (lint & format obbligatori)
Il codice deve essere conforme **prima del commit** a: `black` (format), `isort` (ordinamento import) e `ruff` (lint).

Standard: **line-length 120**, profilo `black` per `isort`, nessun segreto nei log.

**Definition of Done (minimo) per ogni PR):**
- file formattati (`black`) e import ordinati (`isort`);
- `ruff` pulito (nessun F/E/W rilevante);
- **path-safety rispettata** (uso di `ensure_within_and_resolve` & writer sicuri);
- **slug hygiene** (lettura con `get_slug()` o validazione esplicita);
- test esistenti non rotti.

### Linting & Formatting
- Ruff è il linter SSoT: tutte le regole lint vivono in Ruff; se manca qualcosa, estendi `pyproject.toml`.
- Black e isort: obbligatori per formattazione/ordinamento import.

---

## Typing & Pylance
- Per dependency opzionali usa narrowing esplicito:
  - `if fn is None: raise RuntimeError("…")` prima di chiamare funzioni opzionali.
  - Wrapper come `_require_callable(fn, name)` nei layer adapter/runner.
- Evita accessi a metodi su `None` (es. `.strip`): usa normalizzatori tipo `_norm_str`.
- Streamlit: preferisci API stabili (`st.rerun`) con fallback a `experimental_*` solo se assente.
- Type check rapidi: `mypy` e/o `pyright` in CI.

---

## Logging & redazione
- Logger strutturato: `logger.info("event_name", extra={...})` (nessun payload anonimo); popola sempre `extra` con slug/scope/id utili.
- Redazione automatica attiva quando richiesto (`LOG_REDACTION`): non loggare segreti o payload completi.
- Non loggare `os.environ` o credenziali; maschera token/API key.
- Logga eventi chiave in UI (es. `ui.manage.tags.save`).

---

## Sicurezza I/O
- **Path-safety**: usa `ensure_within_and_resolve` (o SSoT equivalenti) per prevenire traversal; evita concatenazioni manuali.
- **Scritture atomiche**: `safe_write_text/bytes` per generare/aggiornare file (niente write parziali).
- **Append sicuro**: `safe_append_text` per audit/log multi-run; garantisce path-safety, lock file e fsync opzionale.
- **Sanitizzazione nomi file**: usa utility dedicate prima di creare file da input esterni.
- **Listing sicuri**: preferisci `iter_pdfs_safe`/`count_pdfs_safe` a `Path.rglob` quando l’input proviene da l’utente.

---

## Orchestratori & UI
- Orchestratori (`pre_onboarding`, `tag_onboarding`, `onboarding_full`) + façade `semantic.api` per la semantica:
  - Niente input bloccanti nei moduli di servizio; tutta la UX rimane negli orchestratori.
  - Gestisci `--non-interactive` per batch/CI.
- UI (onboarding/semantica/manage):
  - Gating su prerequisiti (slug valido, `raw/` presente via `has_raw_pdfs`/`count_pdfs_safe`).
  - **Wrapper UI = firma backend** (test di parità firma consigliati).
  - Niente write manuali: usa writer sicuri e path derivati dal workspace.

---

## Error handling & exit codes
- Solleva **eccezioni tipizzate** (`ConfigError`, `PipelineError`, `PreviewError`, …), non `Exception` generiche.
- Evita `ValueError` ai confini: mappa verso eccezioni di dominio in façade/wrapper.
- In UI mostra errori con messaggi chiari e non verbosi; dettaglio tecnico nei log.

---

## Drive & Git
- Drive: tutte le operazioni passano da runner/adapter dedicati; evita API low-level dirette.
- Download RAW: usa la funzione di alto livello esposta nel runner UI.
- Git: push solo di `.md` in `book/`; ignora `.md.fp` e file binari.

---

## Test
- Genera dataset dummy con `py src/tools/gen_dummy_kb.py --slug dummy`.
- Piramide: unit → middle/contract → smoke E2E (dummy). Niente rete nei test.
- Mocka Drive/Git; verifica invarianti su `book/` e presenza di README/SUMMARY.
- **Nuovi casi minimi obbligatori**:
  - slug invalidi in query/session/persistenza (devono essere scartati);
  - traversal via symlink in `raw/` (gli helper non devono contare file esterni);
  - parità firma wrapper UI ↔ backend.

---

## Versioning & release
- SemVer + `CHANGELOG.md` (Keep a Changelog).
- Aggiorna README e i documenti in `docs/` quando cambi UX/flow.
- Tag/branch coerenti con la policy di versione.

---

## Contributi
- PR piccole, atomic commit, messaggi chiari (imperativo al presente).
- Copri con test i cambi di comportamento; mantieni l’asticella della qualità.

---

## Path-Safety Lettura (Aggiornamento)
- Letture Markdown/CSV/YAML nei moduli `pipeline/*` e `semantic/*`: usa sempre `pipeline.path_utils.ensure_within_and_resolve(base, p)` per ottenere un path risolto e sicuro prima di leggere.
- È **vietato** usare direttamente `open()` o `Path.read_text()` per file provenienti dalla sandbox utente senza passare dal wrapper.
