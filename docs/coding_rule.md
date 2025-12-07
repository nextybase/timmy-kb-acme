# Coding Rules  v1.0 Beta

> **TL;DR:** consulta queste regole prima di toccare pipeline o UI: usa gli helper SSoT, niente side-effect a import-time, logging e path-safety sono vincolanti.

Regole di sviluppo per **Timmy KB**. Questa e la base iniziale: nessun riferimento a legacy o migrazioni. Obiettivo: codice coerente, sicuro e riproducibile.

---

## 1) Principi
- **SSoT (Single Source of Truth)** per configurazioni, dipendenze, logging e I/O.
- **Logging strutturato centralizzato** con redazione segreti.
- **Path-safety** e **scritture atomiche** su ogni file.
- **UI import-safe** (nessun side-effect a import-time).
- **Parita di firma** dei wrapper UI rispetto al backend (`pipeline.*`, `semantic.*`).

---

## 2) Stile & Convenzioni
- **Python  3.11**, tipizzazione obbligatoria per API pubbliche e funzioni non-trivial.
- **Evita `Any`** salvo casi motivati e documentati (commento o docstring dedicata).
- Docstring **Google style** o **PEP257**; `Raises:` per eccezioni rilevanti.
- **Import order**: stdlib  third-party  locali; usa `isort`/`ruff`.
- **Line length**: 120.
- Nomi chiari e stabili; evita abbreviazioni opache.
- Non introdurre global state; preferisci dipendenze **iniettate** (es. logger, base_dir).

Esempio docstring:
```python
def load_reviewed_vocab(base_dir: Path, log) -> dict[str, str]:
    """Load canonical tags from reviewed YAML.

    Args:
      base_dir: Workspace del cliente (radice `output/timmy-kb-<slug>`).
      log: Logger strutturato.

    Returns:
      Mappa canonealias.
    """
```

---

## 2bis) API di modulo
- Esporta l'interfaccia pubblica esplicitando `__all__ = [...]` quando il modulo e consumato da terzi.
- Per i parametri contestuali complessi preferisci `Protocol` o `TypedDict` locali per descrivere il contratto.
- Mantieni chiara la separazione tra API pubbliche e helper `_private`.

---

## 3) Logging (centralizzato)
- Usa **solo** `pipeline.logging_utils.get_structured_logger`.
- **Vietati**: `print`, `logging.basicConfig`, `logging.getLogger(...)`.
- Log in `output/timmy-kb-<slug>/logs/` con `run_id` opzionale.
- Redazione automatica dei segreti quando `LOG_REDACTION` e attivo.
- Formatter **key=value**, handler **idempotenti** (console/file).

Esempio:
```python
from pipeline.logging_utils import get_structured_logger

log = get_structured_logger(__name__, run_id=None, context={"slug": "acme"})
log.info("semantic.index.start", extra={"slug": "acme"})
```

**Livelli suggeriti**: `debug` (diagnostica), `info` (milestones), `warning` (degrado controllato), `error` (recuperabile), `critical` (escalation).

---

## 4) Dipendenze (pip-tools)
- Pin esclusivamente in `requirements*.txt`/`constraints.txt` **generati** da `pip-compile`.
- Modifichi i sorgenti `requirements*.in` e rigeneri con:
```bash
pip-compile requirements.in
pip-compile requirements-dev.in
pip-compile requirements-optional.in
```
- Installazioni standard:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt
```
- **Extras** per ambienti non pin-locked: `pip install .[drive]` o `pip install -e ".[drive]"` (dev).

**Policy**: niente `pip install` adhoc nei documenti o script; nessun pin manuale in `pyproject.toml` oltre al minimo necessario.

---

## 5) I/O sicuro & Path-safety
- Deriva i path **solo** dagli helper della pipeline; non costruire stringhe manualmente verso `output/`.
- Valida e risolvi i path prima dell'uso; scritture **atomiche**.
- Mai seguire symlink non attesi in `raw/`/`book/`.

Esempio:
```python
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.file_utils import safe_write_text

yaml_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml")
safe_write_text(yaml_path, yaml_content, encoding="utf-8", atomic=True, fsync=False)
```

---

## 6) Error handling
- Usa eccezioni **specifiche** del dominio quando presenti (es. `ConfigError`, `PreviewError`, `PushError`).
- Non catturare eccezioni generiche senza rilanciarle/loggarle.
- Nei moduli interni e vietato usare `sys.exit()`/`input()`; solo gli orchestratori CLI gestiscono il processo.
- Mappa gli esiti in **exit codes** standard laddove previsto (0/2/30/40).

---

## 7) UI/Service Layer
- Import-safe: nessun I/O o `load_dotenv()` a livello di modulo.
- Configurazioni lette tramite helper (es. `ui.config_store.get_vision_model()`).
- I wrapper UI **non cambiano** semantica o default del backend; passano i parametri 1:1.
- Il logger viene creato per modulo e **passato** lungo la call-chain.

---

## 8) Test & Qualita
- **Piramide**: unit  contract/middle  smoke E2E (dataset dummy, senza rete).
- Casi minimi **obbligatori**:
  - Slug invalidi  rifiutati/normalizzati.
  - Traversal via symlink in `raw/`  negato.
  - Parita di firma wrapper UI  backend.
  - Invarianti su `book/` (solo `.md` tracciati; `README.md`/`SUMMARY.md` sempre presenti; eventuali `.md.fp` restano locali e non vengono commessi).
- Tooling: `ruff`, `black`, `isort`; type-check con `mypy`/`pyright`.
- Hook:
```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
make qa-safe
make ci-safe
```

### Prompt Chain e QA
Se la modifica deriva da una Prompt Chain Codex, la chiusura richiede:

- successo di `pre-commit run --all-files` e `pytest -q`;
- proposta del commit one-line finale da parte di Codex, come descritto in `docs/PromptChain_spec.md`.

Solo dopo questa fase la modifica e pronta per PR.

---

## 9) Sicurezza & Segreti
- Mai loggare token o credenziali **in chiaro**; affidati alla redazione automatica.
- Le chiavi si leggono da ENV (`OPENAI_API_KEY`); altri meccanismi legacy non sono piu supportati.
- Evita di serializzare payload sensibili in file temporanei non necessari.

---

## 10) Git & PR Policy
- Commit **atomici**, messaggi all'imperativo presente (EN o IT).
- PR piccole con descrizione dello scope e checklist QA.
- Ogni modifica di comportamento va coperta da test; documentazione aggiornata **nello stesso PR**.
- Branch di lavoro: `feat/*`, `fix/*`, `chore/*`, `docs/*`.
- Se la PR nasce da una Prompt Chain Codex, nel corpo PR includi il riferimento alla chain e la conferma che il Prompt finale di QA e stato eseguito con successo secondo `docs/PromptChain_spec.md`.

---

## 11) Pattern da evitare
- Hardcode del modello LLM nei servizi (`MODEL = "gpt-..."`): usare `get_vision_model()`.
- Uso di `print` per log o debug persistente.
- Scritture non atomiche o senza validazione path.
- Side-effect a import-time (I/O, configurazioni globali).
- Wrapper UI che cambiano default o filtrano parametri del backend.

---

## 12) Esempi rapidi
**Chiamata AI (Responses API) con modello da config:**
```python
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

**Scrittura YAML sicura + log evento:**
```python
from pipeline.logging_utils import get_structured_logger
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve

log = get_structured_logger("ui.manage.tags")
yaml_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml")
safe_write_text(yaml_path, yaml_content, encoding="utf-8", atomic=True)
log.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
```

> Quando esporti `tags_reviewed.yaml` da database (`export_tags_yaml_from_db`) oppure quando la UI genera il file YAML, la piattaforma valida tutti i path: workspace -> `semantic/` -> `tags_reviewed.yaml` -> `tags.db`. Se il DB vive fuori dal workspace o non corrisponde al YAML il flusso si blocca con `ConfigError`, cosi nessun export puo scavalcare la sicurezza di path.

---

## 13) Checklist PR (minima)
- [ ] Logging con `get_structured_logger` (niente `print/basicConfig`).
- [ ] Path validati con helper e scritture atomiche.
- [ ] Test aggiornati/aggiunti (unit/contract/smoke).
- [ ] Requirements rigenerati se toccate le dipendenze (`*.in`  `pip-compile`).
- [ ] Documentazione aggiornata (README / Developer Guide / Coding Rules).
