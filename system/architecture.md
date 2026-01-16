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

### Vincoli di design (invarianti del runtime)

- **Path-safety e scritture atomiche**
  - **Invariante:** ogni operazione di I/O su filesystem deve essere confinata
    all'interno del workspace attivo e produrre scritture atomiche.
  - **Enforcement:** garantito quando si utilizzano esclusivamente le utility SSoT
    (`ensure_within*`, `safe_write_*`).
  - **Verifica:** copertura di test parziale su casi di traversal e scrittura;
    non tutte le possibili violazioni sono intercettate automaticamente.
  - **Gap noto:** l'invariante è violabile se moduli aggirano le utility SSoT.

- **Assenza di side effects a import-time**
  - **Invariante:** nessuna operazione di I/O o mutazione di stato globale
    durante l'import dei moduli runtime.
  - **Enforcement:** applicato per convenzione di codice e review;
    alcune violazioni sono intercettate da test architetturali.
  - **Verifica:** non esaustiva; la completezza non è dimostrata automaticamente.

### Policy operative (enforcement parziale)

- **Configurazione runtime centralizzata**
  - **Regola:** la configurazione runtime è letta esclusivamente tramite
    `Settings` / `ClientContext` (SSoT).
  - **Enforcement:** applicato nei punti principali del runtime.
  - **Verifica:** non tutti i punti di accesso sono verificabili automaticamente.

- **Logging strutturato**
  - **Regola:** uso esclusivo di logging strutturato nei moduli runtime;
    `print` vietato.
  - **Enforcement:** verificato per convenzione e tooling.

- **Decisione Beta (gestione dello stato)**
  - La repository contiene solo artefacts versionati.
  - Lo stato runtime vive in workspace esterni deterministici,
    derivati da `WorkspaceLayout`.

## Tracciabilita (esempi, non esaustivi)

> Nota: i riferimenti seguenti sono indicativi e non costituiscono
> una SSoT architetturale. L'invariante è la regola, non il path del file.

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

## Stato degli invarianti (v1.0 Beta)

| Invariante                         | Stato        | Note sintetiche                          |
|-----------------------------------|--------------|------------------------------------------|
| Path-safety                       | Implemented  | Utility SSoT + test parziali              |
| Scritture atomiche                | Implemented  | Enforcement via utility                  |
| No side effects a import-time     | Guardrailed  | Test architetturali non esaustivi         |
| Config via Settings/ClientContext | Observed     | Enforcement parziale                     |
| Logging strutturato               | Implemented  | Tooling + convenzione                    |
