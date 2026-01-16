# Import Contract (namespace unico)

Timmy-KB adotta un namespace unico top-level. Questo contratto blocca definitivamente il doppio percorso legacy e fissa le regole di import per il runtime e per i tool.

## Scopo
- Definire i package legittimi e vietare il ricorso al namespace legacy in qualsiasi forma.
- Impedire giochi di `sys.path` nei moduli applicativi.
- Chiarire che `tools/` è la SSoT e non esistono fallback al vecchio namespace.

## Package ammessi (runtime)
- `pipeline.*` (helper core: context, workspace, path safety, logging, drive/github).
- `semantic.*` (convert/enrich/embedding/mapping/tagging).
- `ui.*` (Streamlit app/pages/services).
- `tools.*` (tooling ufficiale: smoke, generatori, diagnostica) - **unico SSoT**.

## Divieti
- Vietato importare o risolvere stringhe del namespace legacy in qualsiasi modulo (inclusi `importlib`, loader custom, plugin).
- Vietato manipolare `sys.path` nei moduli applicativi. Consentito solo nei runner/entrypoint **se strettamente indispensabile** e con commento che spiega il motivo.
- Vietato usare shim o alias verso namespace legacy o percorsi legacy.

## Tools: Single Source of Truth
- `tools/` è l'unica sorgente runtime per `tools.*`.
- Il vecchio namespace non è più sorgente: nessun import, nessun fallback, nessun loader.
- Le dipendenze interne tra tool devono usare import espliciti `from tools...` senza path hacking.

## Esempi
- Corretto:
  - `from pipeline.workspace_layout import WorkspaceLayout`
  - `import pipeline.workspace_layout as wl`
  - `import semantic.api as semantic_api`
  - `importlib.import_module("tools.gen_dummy_kb")`
  - `from tools.gen_dummy_kb import build_payload`
- Errato:
  - `importlib.import_module("legacy_ns.tools.gen_dummy_kb")`
  - hacking di `sys.path` nei moduli applicativi

## Enforcement rapido
- Trova violazioni del namespace legacy negli import:
  - `rg 'from\\s+legacy_ns\\.|import\\s+legacy_ns\\.'`
  - `rg 'importlib\\.import_module\\(\"legacy_ns\\.'`
- Trova path hacking:
  - `rg 'sys\\.path' src tools`
- Conferma SSoT tools:
  - `rg 'legacy_ns\\.tools'`

## Test da eseguire
- Suite rapida: `pytest -q -k "not slow"`
- Se tocchi Streamlit/UI: aggiungi `-m "not slow"` con filtri di pagina se servono.
- Prima della chiusura finale della Prompt Chain: `pre-commit run --all-files` + `pytest -q`.

## Note operative
- Runner/entrypoint (es. CLI Streamlit/pytest) possono toccare `sys.path` solo se non c'è alternativa e devono documentare il motivo; i moduli di libreria non possono farlo.
- Documentare ogni eccezione nel changelog e rimuovere i workaround appena possibile.
