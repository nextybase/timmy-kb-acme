# System Architecture

> **Authority:** questo documento è il riferimento canonico per la mappa dei
> componenti e delle responsabilità. Le guide narrative devono linkare qui e non
> duplicare i contenuti. Per regole tecniche e di stile vedi
> [docs/developer/coding_rule.md](../docs/developer/coding_rule.md).

This document defines:
- the architectural invariants of the Timmy-KB runtime,
- the execution model and responsibility boundaries,
- an explicit repository map (directories and files) to support deterministic usage.

Note:
This document **does not replace** governance rules defined in `instructions/*` or principles defined in `MANIFEST.md`.
However, it **does explicitly map** the repository and runtime structure, because for a deterministic system
the filesystem layout is part of the architecture, not an implementation detail.
Determinism here refers to runtime execution, I/O, and enforcement paths;
epistemic probabilism remains defined in `MANIFEST.md`.

## Repository Map (Root Level)

The repository is structured to separate:
- runtime core,
- control plane governance,
- documentation,
- tooling and tests.

### src/
Core runtime application code (installable package).
All production execution logic originates here.

### system/
System-facing documentation:
- architectural overview,
- execution model,
- operational notes for the prompt chain.
This directory is descriptive and operational, not normative.
In case of conflict, `instructions/*` takes precedence.

### instructions/
Normative control-plane source of truth (SSoT):
- roles and responsibilities,
- state machines and gates,
- allowed transitions,
- failure modes and invariants.

If a behavior is not described here (or in MANIFEST.md),
it must be considered unsupported.

### docs/
Descriptive documentation (user, developer, policy, ADR).
Used for onboarding and context, not for enforcement.

### tools/
Operational tooling and smoke utilities.
Explicitly **excluded** from the production runtime.
Best-effort and non-deterministic fallback behavior is allowed only here.

### tests/
Automated tests and governance enforcement (e.g. gate acknowledgements).
Do not define runtime behavior.

### config/
Versioned configuration templates and defaults.
Secrets are never stored here.

### observability/
Local observability stack (e.g. Loki/Grafana/Promtail).
Consumes logs produced in workspace directories.

### .github/
Repository governance (CI, ownership, policies).

### .codex/
Prompt-chain workflows and agent tooling.

## Source Map (src/)

The `src/` directory contains the entire production runtime.
Each subdirectory has a defined responsibility and boundary.

### src/pipeline/
Deterministic runtime foundation.

Responsibilities:
- path-safety and perimeter enforcement,
- atomic I/O,
- logging initialization,
- runtime configuration loading,
- workspace layout validation.

This layer contains the **core deterministic guarantees** of the system.

Key single sources of truth (SSoT):
- `workspace_layout.py`
- `context.py`
- `path_utils.py`
- `file_utils.py`

No other module is allowed to replicate or bypass their logic.

### src/timmy_kb/
Application layer and entry points:
- CLI commands,
- UI wiring,
- orchestration glue.

This layer must delegate all filesystem and state logic to `pipeline/`.

### src/ui/
Streamlit-based UI.
Acts as a thin facade over backend functions.
Must preserve backend signatures and semantics.

### Streamlit UI Startup (Phase 0)
Before logging, preflight, or navigation, the UI entrypoint must load `.env`
via `pipeline.env_utils.ensure_dotenv_loaded()` to stabilize workspace resolution.
The operation is idempotent and must not create repeated startup logs.

### src/semantic/
Semantic transformation and enrichment:
- content conversion,
- tagging and validation,
- generation of semantic artifacts.

Must resolve paths through `WorkspaceLayout`, never via ad-hoc joins.

### src/ai/
LLM and Assistant integration:
- assistant/model resolution,
- client factory,
- AI-side configuration resolution.

This layer does not own persistence or workspace layout.

### src/storage/
Persistence layer (SSoT data):
- knowledge base storage,
- tag databases.

All paths are workspace-scoped.
Global fallbacks are explicitly forbidden.

### src/security/
Runtime hardening:
- slug isolation,
- masking,
- throttling,
- retention.

### src/adapters/
Adapters to external tools or services.
Must follow pipeline guarantees and path-safety.

### src/explainability/
Explainability artifacts:
- lineage,
- evidence packets,
- explainability manifests.

### src/nlp/
NLP utilities and helpers.
May have optional dependencies, but must fail explicitly if missing.

## Runtime Deterministic Core (Single Sources of Truth)

The Timmy-KB runtime is deterministic by design.
Determinism is enforced by a small set of core modules.

These modules are **Single Sources of Truth (SSoT)** and must never be bypassed.

### Workspace Layout (SSoT of structure)
Module: `pipeline/workspace_layout.py`

Defines:
- canonical workspace structure,
- required directories and files,
- validation rules.

No module may reconstruct paths manually or assume directory names.

### Execution Context (SSoT of state)
Module: `pipeline/context.py`

Defines:
- slug identity,
- workspace root resolution,
- runtime configuration,
- logging context.

Historical compatibility fields (e.g. `base_dir`, `md_dir`) are **temporary and deprecated**;
they exist only to support legacy paths and **must not be used by new or refactored code**
as authoritative sources.

### Path Safety (SSoT of perimeter)
Module: `pipeline/path_utils.py`

Defines:
- strong path guards (`ensure_within`),
- deterministic sanitization,
- slug validation.

All filesystem writes and destructive operations must be guarded here.

### Atomic I/O (SSoT of persistence)
Module: `pipeline/file_utils.py`

Defines:
- atomic write guarantees,
- fsync behavior,
- explicit and logged fallbacks.

This module does not perform path validation by design;
path safety must be enforced before invoking it.

## Configuration Boundary - Strict Guard Policy

Runtime configuration boundaries must be strict and deterministic.
They must not absorb exceptions, normalize failures into defaults,
or silently downgrade invalid inputs.
If a value is missing, the boundary may return an explicit default only
when the configuration mapping is valid and the path is absent.
Any read or conversion error must raise a typed error (usually `ConfigError`)
and preserve the original cause.

Runtime boundary modules (strict guard):
- `src/ai/assistant_registry.py`
- `src/ai/vision_config.py`
- `src/semantic/vision_provision.py`
- `src/ui/clients_store.py`

## Forbidden Patterns (Beta 1.0)

The following patterns are explicitly forbidden in the production runtime.
They are banned because they already occur in legacy paths and break determinism:

FORBIDDEN: Deriving paths via `context.base_dir`, `context.md_dir`, `context.raw_dir`
ALLOWED: Use `WorkspaceLayout.from_context(context)`

FORBIDDEN: Reconstructing paths via manual joins
ALLOWED: Use layout-provided paths and `ensure_within`

FORBIDDEN: Heuristic reconstruction of workspace roots
(e.g. inferring root from config paths)

FORBIDDEN: Silent or non-deterministic fallbacks in runtime code
All runtime fallbacks must be explicit, logged, deterministic, and documented.
Non-deterministic or best-effort fallback patterns are allowed only in `tools/`.

Any violation of these rules introduces entropy and breaks determinism.

## Responsibilities and boundaries

**Application core (`src/`)**
- `pipeline/`: I/O-safe orchestration, path safety, logging, config, runtime core.
- `semantic/`: conversion, enrichment, tagging, content validation.
- `ui/`: Streamlit UX and gating; delegates to pipeline without changing semantics.
- `ai/`: model/assistant resolution and client factory.
- `security/`: safety controls, masking, throttling, retention.
- `storage/`: persistence SSoT (e.g. KB/tags).
- `timmy_kb/`: CLI/UI entry points and packaging.
- `adapters/`, `explainability/`, `nlp/`: integration and traceability.

**Governance and policy**
- `system/`: system-level architecture and operational documentation (descriptive, non-normative).
- `instructions/`: normative Prompt Chain governance and roles (SSoT).
- `docs/`: reference documentation.

**Tooling and tests**
- `tools/`, `tests/`: operational tooling and tests; do not define production runtime.

## Design and policy constraints

### Design constraints (runtime invariants)

- **Path safety and atomic writes**
  - **Invariant:** every filesystem I/O must remain within the active workspace
    and produce atomic writes.
  - **Enforcement:** guaranteed when exclusively using the SSoT utilities
    (`ensure_within*`, `safe_write_*`).
  - **Verification:** partial test coverage for traversal and writes;
    not all violations are automatically detected.
  - **Known gap:** the invariant is breakable if modules bypass the SSoT utilities.

- **No import-time side effects**
  - **Invariant:** no I/O or global state mutation during runtime module import.
  - **Enforcement:** code convention and review;
    some violations are caught by architecture tests.
  - **Verification:** not exhaustive; completeness is not automatically proven.

### Operational policies (partial enforcement)

- **Centralized runtime configuration**
  - **Rule:** runtime configuration is read only through
    `Settings` / `ClientContext` (SSoT).
  - **Enforcement:** applied at the main runtime entry points.
  - **Verification:** not all access points are automatically checkable.

- **Structured logging**
  - **Rule:** structured logging only in runtime modules; `print` is forbidden.
  - **Enforcement:** code convention and tooling.

- **Beta decision (state management)**
  - The repository contains only versioned artifacts.
  - Runtime state lives in deterministic external workspaces,
    derived from `WorkspaceLayout`.

## Traceability (examples, non exhaustive)

> Note: the references below are illustrative and do not constitute
> an architectural SSoT. The invariant is the rule, not the file path.

- Path safety: `src/pipeline/path_utils.py`
- Atomic writes: `src/pipeline/file_utils.py`
- Runtime config: `src/pipeline/settings.py`, `src/pipeline/context.py`
- Workspace layout: `src/pipeline/workspace_layout.py`
- Assistant/model resolution: `src/ai/assistant_registry.py`, `src/ai/resolution.py`
- Client factory: `src/ai/client_factory.py`

## Execution model

1. **Foundation pipeline**: transforms input into deterministic outputs
   (derivatives), validates and produces the knowledge graph baseline;
   it does not decide or govern.
2. **UI/CLI**: orchestrate flows with explicit gating and call the pipeline.
3. **Control plane**: the Prompt Chain and HiTL gates define governance and
   operation order (Planner/OCP/Codex), without bypassing the pipeline.

## Invariant status (v1.0 Beta)

| Invariant                         | Status       | Notes                                      |
|----------------------------------|--------------|--------------------------------------------|
| Path safety                       | Implemented  | SSoT utilities + partial tests             |
| Atomic writes                     | Implemented  | Enforcement via utilities                  |
| No import-time side effects       | Guardrailed  | Architecture tests are not exhaustive      |
| Config via Settings/ClientContext | Observed     | Partial enforcement                        |
| Structured logging                | Implemented  | Tooling + convention                       |

## SSoT and forbidden patterns summary

| Area                   | SSoT module                      | Responsibility                          |
|------------------------|----------------------------------|------------------------------------------|
| Workspace structure    | `pipeline/workspace_layout.py`   | Canonical layout + validation            |
| Execution state        | `pipeline/context.py`            | Slug identity + runtime context          |
| Path safety perimeter  | `pipeline/path_utils.py`         | Path guards + sanitization               |
| Atomic persistence     | `pipeline/file_utils.py`         | Atomic writes + fsync policy             |

| Rule type   | Forbidden pattern                                           | Required alternative                      |
|------------|--------------------------------------------------------------|-------------------------------------------|
| Paths       | Use `context.base_dir` / `context.md_dir` / `context.raw_dir` | `WorkspaceLayout.from_context(context)`   |
| Paths       | Manual path joins                                            | Layout-provided paths + `ensure_within`   |
| Roots       | Heuristic workspace root inference                           | Resolve via context + layout              |
| Fallbacks   | Silent or non-deterministic fallback in runtime code          | Explicit, logged, deterministic fallback  |
