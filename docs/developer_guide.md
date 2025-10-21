## Developer Guide — Facade & Wrapper Audit (2025‑10‑07)

### Audit dei Wrapper che Delegano a `pipeline.*`

Un audit mirato è stato condotto sul repository `timmy-kb-acme` per identificare tutti i wrapper UI che delegano a funzioni della pipeline centrale. I risultati confermano che la maggior parte dei moduli UI segue correttamente il contratto SSoT (Single Source of Truth), ma alcuni richiedono un riallineamento di firma per garantire piena parità futura.

#### Risultati principali

**1. `src/ui/utils/core.py`**
- Wrappers individuati: `safe_write_text`, `ensure_within_and_resolve`, `to_kebab`, `yaml_load`, `yaml_dump`.
- Stato: ✅ coerenti con la pipeline tranne `safe_write_text`, che inizialmente non esportava il parametro `fsync`.
- Correzione applicata: la firma è stata aggiornata a `safe_write_text(path, data, *, encoding='utf-8', atomic=True, fsync=False)` per mantenere parità con `pipeline.file_utils.safe_write_text`.

**2. `src/ui/components/yaml_editors.py`**
- Wrapper: `safe_write_text` usato per scritture atomiche.
- Stato: ✅ coerente (parametri `encoding`, `atomic`, `fsync=False` ora supportati a cascata dal wrapper core).

**3. `src/ui/services/tags_adapter.py`**
- Wrapper: `safe_write_text` e `ensure_within_and_resolve`.
- Stato: ✅ corretti; nessuna divergenza di firma.

**4. `src/ui/clients_store.py`**
- Wrapper: `safe_write_text` e `ensure_within_and_resolve`.
- Stato: ✅ coerenti; usa parametri di default identici alla pipeline.

### Linee Guida Aggiornate per Facade/Wrapper

Per prevenire divergenze future, ogni *facade* o *wrapper* che delega a moduli `pipeline.*` deve:

1. **Mantenere la stessa firma** del backend SSoT (nomi, posizione e default dei parametri).
2. **Delegare senza alterazioni semantiche**: nessuna modifica dei default, nessun filtraggio dei parametri opzionali.
3. **Riesporre nuove feature** introdotte nel backend entro lo stesso commit (es. nuovi flag come `fsync`, `retry`, `atomic`).
4. **Essere coperto da test di parità firma**, ad esempio:
   ```python
   def test_safe_write_text_signature_matches_backend():
       import inspect, importlib
       ui = importlib.import_module('src.ui.utils.core')
       be = importlib.import_module('pipeline.file_utils')
       assert inspect.signature(ui.safe_write_text) == inspect.signature(be.safe_write_text)
   ```
5. **Aggiungere un test di pass-through comportamentale** per garantire che tutti i parametri (inclusi quelli opzionali) vengano trasmessi correttamente.

# Sezione: LLM — Modello per chiamate *dirette* (SSoT in `config/config.yaml`)

Questa sezione spiega **come leggere il modello LLM da un’unica fonte di verità** quando fai **chiamate dirette** (es. `responses`/`chat.completions`) senza passare da l’Assistant preconfigurato.

> **Quando serve**: solo per feature UI/servizi che invocano l’LLM direttamente. Il flusso **Vision → Assistant** continua a usare l’`assistant_id` e **non** legge `vision.model`.

---

## 1) Configurazione: `config/config.yaml`

Configurazione base:

```yaml
vision:
  model: gpt-4o-mini-2024-07-18   # unico riferimento (SSoT)
  strict_output: true              # se rilevante per la tua chiamata
  assistant_id_env: OBNEXT_ASSISTANT_ID  # usato SOLO dal flusso con Assistant
```

- `vision.model` è il **modello** per le chiamate LLM dirette.
- `assistant_id_env` è ignorato nelle chiamate dirette (serve solo all’Assistant).

---

## 2) Helper UI: leggere il modello da config&#x20;

**File:** `src/ui/config_store.py`

```python
from pathlib import Path
import yaml

# ... resto del file ...

def get_vision_model(default: str = "gpt-4o-mini-2024-07-18") -> str:
    """Legge vision.model da config/config.yaml (SSoT UI)."""
    cfg_path = get_config_path()
    data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    vision = (data.get("vision") or {})
    return str(vision.get("model") or default)
```

> Per ambienti multi‑tenant/override, puoi far puntare `get_config_path()` a file diversi via env.

---

## 3) Uso nei service UI che chiamano l’LLM

**Esempio:** `src/ui/services/<feature>_llm.py`

```python
from timmykb.ui.config_store import get_vision_model
from timmykb.ai.client_factory import make_openai_client

MODEL = get_vision_model()  # ← NIENTE hardcode

client = make_openai_client()

# Esempio A: Responses API (structured text output)
resp = client.responses.create(
    model=MODEL,
    input=[
        {"role": "system", "content": "Sei un assistente.."},
        {"role": "user",   "content": "<prompt dell’utente>"},
    ],
)
text = resp.output_text

# Esempio B: Chat Completions (se usi l’API chat)
# chat = client.chat.completions.create(
#     model=MODEL,
#     messages=[
#         {"role": "system", "content": "Sei un assistente.."},
#         {"role": "user",   "content": "<prompt dell’utente>"},
#     ],
# )
# text = chat.choices[0].message.get("content", "")
```

**Linee guida**:

- Non hardcodare il modello nei servizi; usa sempre `MODEL = get_vision_model()`.
- Se cambi modello (p.es. in stage/prod), basta aggiornare `config/config.yaml`.
- Mantieni `strict_output`/validazioni nel servizio se il contratto di output lo richiede (JSON, ecc.).

---

## 4) Differenze con il flusso *Assistant*

- **Assistant (Vision)**: legge l’`assistant_id` da env (nome della variabile preso da `vision.assistant_id_env`), e il modello è configurato **dentro** l’Assistant. `vision.model` **non** è usato.
- **Chiamate dirette**: ignorano `assistant_id_env` e usano **sempre** `vision.model`.

Schema decisionale rapido:

- Se stai usando `client.beta.threads.runs.create_and_poll(... assistant_id=...)` → **Assistant** (usa `assistant_id_env`).
- Se stai usando `client.responses.create(... model=...)` o `client.chat.completions.create(... model=...)` → **diretto** (usa `get_vision_model()`).

---


## 5) Anti‑pattern da evitare

- Hardcodare `MODEL = "gpt‑..."` nei file di servizio.
- Leggere il modello da env sparse (es. `LLM_MODEL`) bypassando `config.yaml`.
- Ri‑risolvere il path di `config.yaml` in ogni funzione: usa `get_config_path()` dal `config_store`.

---

## 6) FAQ

- **Posso usare modelli diversi per feature diverse?**\
  Sì, ma tieni la regola: ogni feature legge il suo modello dal `config.yaml`. Se servono due modelli, aggiungi un sotto‑blocco (es. `vision.preview.model`, `vision.qa.model`) e due getter dedicati.

- **Cosa succede se ************`vision.model`************ manca?**\
  Il getter ritorna il default (`gpt-4o-mini-2024-07-18`). Imposta sempre un valore esplicito in produzione.


### Prossimi Step
- Introdurre un test automatico di “Signature Parity” per tutti i wrapper UI.
- Aggiornare la sezione *CI Quality Checks* per includere un controllo di coerenza SSoT.

---

## Estensione Audit — Modulo `services/*`

> Obiettivo: verificare i wrapper/logiche adattatrici in `src/ui/services` che delegano a `pipeline.*` o ad altre SSoT (es. `semantic.*`).

### Copertura e Risultati

**1) `services/tags_adapter.py`**
- Deleghe: `ensure_within_and_resolve`, `safe_write_text` (per persistenza mapping/tag review).
- Stato: **OK** — firma allineata grazie al ripristino di `fsync` nel wrapper UI; i default coincidono con il backend.

**2) `services/workspace_utils.py` (o equivalenti)**
- Deleghe: path‑safety (`ensure_within*`), discovery cartelle/asset.
- Stato: **OK** — usa le guardie SSoT senza ridefinire parametri; nessun comportamento divergente trovato.
- Nota: dove possibile preferire `validate_slug` (dalla pipeline) invece di normalizzazioni locali.

**3) `clients_store.py` / `services/clients_store.py`**
- Deleghe: `safe_write_text`, `ensure_within_and_resolve`.
- Stato: **OK** — la persistenza ora può opt‑in su `fsync=True` in operazioni sensibili (es. salvataggi di configurazioni/indici).

**4) Adapter verso `semantic.*` (es. enrichment/indexer)**
- Deleghe: chiamate a facade `semantic.api` con parametri pass‑through.
- Stato: **OK** — nessun rimappaggio dei default; i wrapper non nascondono flag rilevanti.

> Non sono emersi altri wrapper con divergenza di firma rispetto alle SSoT. In caso di introduzione di nuove utility in pipeline (es. `safe_append_text(fs...)`, `retry_write(...)`), la UI **deve** riesporre i nuovi argomenti con gli stessi default.

### Linee guida aggiuntive per `services/*`
- **Parità di firma**: ogni funzione di `services/*` che è un semplice inoltro verso pipeline/semantic deve mantenere names/default **identici**.
- **No side‑effects**: nessun monkeypatch o rebinding globale; preferire `partial` o parametri espliciti.
- **Idempotenza**: le funzioni che scrivono su disco devono essere ri‑eseguibili senza effetti collaterali (scritture atomiche, cleanup, path‑safety).
- **Errori tipizzati**: propagare `ConfigError`/`PipelineError` senza trasformarli in `ValueError` generici.

### Test proposti (aggiuntivi)
- **Signature Parity per services**
  ```python
  import importlib, inspect
  from typing import Sequence

  CASES: Sequence[tuple[str, str, str]] = (
      ("src.ui.services.tags_adapter", "safe_write_text", "pipeline.file_utils.safe_write_text"),
      ("src.ui.services.tags_adapter", "ensure_within_and_resolve", "pipeline.path_utils.ensure_within_and_resolve"),
  )

  def _sig(fn):
      return tuple((p.kind, p.name, p.default is not inspect._empty) for p in inspect.signature(fn).parameters.values())

  def test_services_signature_parity():
      for mod_name, fn_name, be_path in CASES:
          mod = importlib.import_module(mod_name)
          be_mod_name, be_fn_name = be_path.rsplit(".", 1)
          be_mod = importlib.import_module(be_mod_name)
          assert _sig(getattr(mod, fn_name)) == _sig(getattr(be_mod, be_fn_name))
  ```
- **Pass‑through comportamentale** (es.: `safe_write_text(..., fsync=True)` chiama il backend con `fsync=True`).

Con questa estensione, anche i wrapper/adapter in `services/*` risultano allineati alle SSoT, riducendo il rischio di drift e rendendo la UI più prevedibile ai rerun.
