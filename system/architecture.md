# Architettura del repository (v1.0 Beta)

Questo documento descrive solo l'architettura: responsabilita, confini, invarianti
e modello di esecuzione. Non inventaria directory o artefatti locali.

## Responsabilita e confini

**Core applicativo (`src/`)**
- `pipeline/`: orchestrazione I/O-safe, path-safety, logging, config e runtime core.
- `semantic/`: conversione, arricchimento, tagging, validazione contenuti.
- `ui/`: UX Streamlit e gating; delega alla pipeline senza cambiare semantica.
- `ai/`: risoluzione modelli/assistant e client factory.
- `security/`: controlli di sicurezza, masking, throttling, retention.
- `storage/`: persistenza SSoT (es. KB/tags).
- `timmy_kb/`: entrypoint CLI/UI e packaging.
- `adapters/`, `explainability/`, `nlp/`: integrazione e tracciabilita.

**Governance e policy**
- `system/`: specifiche e policy di sistema (SSoT).
- `instructions/`: governance Prompt Chain e ruoli.
- `docs/`: documentazione di riferimento.

**Tooling e test**
- `tools/`, `tests/`: tooling operativo e test; non definiscono il runtime di produzione.

## Vincoli di design e policy

- **Vincolo di design (enforced in core utilities; test coverage non garantita):**
  path-safety e scritture atomiche tramite utility SSoT (`ensure_within*`,
  `safe_write_*`).
- **Vincolo di design (enforced in code; test coverage non garantita):** nessun
  side effect a import-time; I/O solo in funzioni/runtime.
- **Policy operativa:** configurazione runtime letta solo via Settings/ClientContext
  (SSoT). Non tutti i punti sono verificabili automaticamente.
- **Policy operativa:** logging strutturato; niente `print` nei moduli runtime.
- **Decisione Beta (policy):** la repo contiene solo artefacts versionati; lo stato
  runtime vive in workspace esterni deterministici (derivati da WorkspaceLayout).

## Tracciabilita (esempi, non esaustivi)

- Path-safety: `src/pipeline/path_utils.py`
- Scritture atomiche: `src/pipeline/file_utils.py`
- Config runtime: `src/pipeline/settings.py`, `src/pipeline/context.py`
- Workspace layout: `src/pipeline/workspace_layout.py`
- Risoluzione assistant/model: `src/ai/assistant_registry.py`, `src/ai/resolution.py`
- Client factory: `src/ai/client_factory.py`

## Modello di esecuzione

1. **Foundation pipeline**: trasforma input in output deterministici (derivatives),
   valida e produce le basi del knowledge graph; non decide, non governa.
2. **UI/CLI**: orchestrano i flussi con gating esplicito e chiamano la pipeline.
3. **Control plane**: Prompt Chain e gate HiTL definiscono governance e ordine
   delle operazioni (Planner/OCP/Codex), senza bypassare la pipeline.
