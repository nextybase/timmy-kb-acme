# System Architecture

> **Authority:** questo documento è il riferimento canonico per la mappa dei
> componenti e delle responsabilità. Le guide narrative devono linkare qui e non
> duplicare i contenuti. Per regole tecniche e di stile vedi
> [docs/developer/coding_rule.md](../docs/developer/coding_rule.md).

This document describes the runtime architecture of Timmy-KB and its
alignment with the system's epistemic foundations.

Timmy-KB is architected around **two distinct and non-overlapping epistemic domains**:

- **Epistemic Envelope**
- **Agency Engine**

These domains are not implementation details, but **first-class architectural concepts**.
All runtime components, pipelines and execution models are subordinate to this separation.

The Epistemic Envelope and the Agency Engine both rely on AI-based inference,
but are strictly separated by the presence or absence of *agency*.

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

## Epistemic Domains Overview

| Epistemic Domain     | Role                              | Nature of inference           |
|----------------------|-----------------------------------|-------------------------------|
| Epistemic Envelope   | Knowledge foundation & constraints| Inferential, non-deliberative |
| Agency Engine        | Decision & action orchestration   | Inferential, deliberative     |

Any violation or blurring of this separation constitutes an architectural error.

## Execution Model Overview

The system execution model is composed of two main layers,
which are **architectural realizations** of the two epistemic domains:

- **Foundation Pipeline** → implementation of the *Epistemic Envelope*
- **Control Plane** → implementation of the *Agency Engine*

These layers are intentionally asymmetric in behavior and guarantees.

## Epistemic Envelope (Foundation Pipeline)

The **Epistemic Envelope** is implemented through the Foundation Pipeline
and the deterministic runtime core.

Its responsibility is to transform raw inputs into normalized markdown and structured, observable
and explainable informational artifacts:

- normalized and chunked markdown
- metadata
- semantic representations
- knowledge graphs
- ledgers and lineage

Inference is allowed exclusively in a **descriptive and constructive form**.
No decisions, selections or goal-oriented actions are permitted in this domain.

All operations within the Epistemic Envelope must be:
- deterministic at the operational level
- strictly observable
- reproducible and auditable

Low-entropy invariants are enforced at write-time by the ledger boundary, so any deviation explodes deterministically when the emission is attempted.

The `raw_ingest` pipeline supports two provisioning modes (`drive` and `local`), but once the PDF sources are materialized in `raw/` the normalization flow remains a single deterministic process. Evidence references now capture the provisioning mode (`source:<drive|local>`) and an optional hashed local path token, enabling auditability without leaking sensitive local paths. The transformer service is explicitly locked through the configuration (name/version/ruleset_hash) and any mismatch between the deployed transformer and the lock section aborts early with failure, keeping the ingest deterministic and verifiable.
## Agency Engine (Control Plane)

The **Agency Engine** is implemented through the Control Plane.

It governs agent interactions, prompt chains and deliberative workflows.

This is the domain where *agency is explicitly allowed*.

The Agency Engine is intentionally probabilistic:
- multiple models may be involved
- alternative solutions may be explored
- emergent behavior is permitted

However, its operational context is **strictly bounded** by the Epistemic Envelope.

No agent, prompt or decision may:
- bypass the Epistemic Envelope
- introduce knowledge not derived from it
- invalidate its constraints

## Principle of Asymmetric Cooperation

The intelligence of Timmy-KB does not emerge from either domain in isolation,
but from their **strict separation and asymmetric cooperation**.

- The Epistemic Envelope reduces structural uncertainty.
- The Agency Engine exploits residual uncertainty for controlled exploration.

Any attempt to merge or collapse these domains undermines the system's
epistemic integrity.

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

Not every module under `src/pipeline/` belongs to the operational Epistemic Envelope perimeter.
Some modules are support utilities (for example log viewer and layout summary) classified as service-only: they do not produce core artifacts and are excluded from the strictest entropy constraints applied to deterministic pipeline/semantic/storage/ledger paths.

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

### Dummy bootstrap events & semantics
The dummy bootstrap workflow emits a single ledger event (`dummy_bootstrap`) with `stage="skeleton"`.
It certifies a controlled minimum workspace state:
1. the workspace skeleton is created and bootstrap directories (`raw`, `semantic`, `book`, `config`, `normalized`) exist;
2. a minimal `config/config.yaml` is materialized (merged from template);
3. the `ClientContext` load immediately after the skeleton (post-skeleton) is performed and reused whenever available.
It does **not** certify that Vision, Drive, or full Semantic flows completed; those remain distinct events or logs.
Any `non_strict_step` event is emitted separately to audit a scoped relaxed execution (e.g., `vision_enrichment`) and records only the specific step name, status, and justification.
For Dummy/Smoke contract and allowed exceptions, see `docs/developer/coding_rule.md` (section: "1ter) Dummy Mode (Smoke E2E)").

### Context load entropy policy (Dummy)
Under the Beta contract the dummy bootstrap may call `ClientContext.load` only once in the post-skeleton phase (`_CTX_STAGE_POST_SKELETON`).
That single load serves the strict-output precheck and any config updates; any additional reload is treated as an entropy regression and must be guarded by explicit reasoning (e.g., manual migration instrumentation) before it can be reintroduced.

### Registry root SSoT
The registry and clients store treat the repo root as the single source of truth: `REPO_ROOT_DIR` defines the registry perimeter and is never overridden by `WORKSPACE_ROOT_DIR`.
WORKSPACE_ROOT_DIR remains valid for UI/tooling workspaces, but the registry ignores this override by design and emits a sanitized log (`workspace_root_ignored`) that reports which environment variables were seen (hashed value + length) so operators can debug without leaking deterministic paths.

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

These modules are **Single Sources of Truth (SSoT)** and must never be bypassed. For recent contract alignments see [docs/contract_alignment.md](docs/contract_alignment.md).

### Workspace Layout (SSoT of structure)
Module: `pipeline/workspace_layout.py`

Defines:
- canonical workspace structure,
- required directories and files,
- validation rules.

Phase A/Phase B contract (anti-entropy):
- Phase A (pre-semantic): workspace layout is valid even if `semantic/semantic_mapping.yaml` is missing.
- Phase B+ (semantic workflows): `semantic/semantic_mapping.yaml` is mandatory and must fail-fast if missing.
- Canonical Phase B gate: `WorkspaceLayout.require_phase_b_assets()`.
- Parallel gates based on `mapping.exists()` are non-canonical and must not replace the gate above.

No module may reconstruct paths manually or assume directory names.

### Execution Context (SSoT of state)
Module: `pipeline/context.py`

Defines:
- slug identity,
- workspace root resolution,
- runtime configuration,
- logging context.

Invariant (core deterministico):
- la risoluzione del workspace richiede un root canonico derivato da
  `REPO_ROOT_DIR` oppure `WORKSPACE_ROOT_DIR` (SSoT in `pipeline/env_constants.py`);
  l'assenza di entrambi e' un errore deterministico e fail-fast, non un requisito opzionale.

Beta 1.0 policy (strict-only):
- `ClientContext` exposes **only** the canonical workspace root (`repo_root_dir`) as SSoT.
- Historical compatibility fields (e.g. `base_dir`, `md_dir`, `raw_dir`, `normalized_dir`)
  are considered **legacy shims** and must not exist in production runtime code.
  Any re-introduction of these fields (even as aliases) is treated as a determinism regression.

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

FORBIDDEN: Deriving paths via any legacy context dir fields
  (e.g. `context.base_dir`, `context.md_dir`, `context.raw_dir`, `context.normalized_dir`).
ALLOWED: Resolve all paths via `WorkspaceLayout.from_context(context)` and layout-provided attributes.
NOTE: In Beta 1.0 strict-only, these legacy fields are not part of the runtime `ClientContext` API.

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
| Paths       | Use legacy context dir shims (`base_dir`/`md_dir`/`raw_dir`/`normalized_dir`) | `WorkspaceLayout.from_context(context)`   |
| Paths       | Manual path joins                                            | Layout-provided paths + `ensure_within`   |
| Roots       | Heuristic workspace root inference                           | Resolve via context + layout              |
| Fallbacks   | Silent or non-deterministic fallback in runtime code          | Explicit, logged, deterministic fallback  |
## Execution Model (Beta 1.0): End-to-End Determinism

Beta 1.0 enforces determinism at the level of **process and artifacts**, not at the level of model text.
All critical execution steps MUST be reconstructible from the local ledger (`runs/decisions/events`).

Two end-to-end flows are considered primary for Beta readiness:

1. **Epistemic Envelope Flow (Foundation Pipeline)**
2. **Agency Flow (Control Plane + Assistants)**

These flows are governed by the same strict principles:

- No implicit fallbacks
- No silent degradation
- Stop/resume is ledger-governed, not UI-governed

---

## Flow A -- Epistemic Envelope (Ingest → Normalize → Semantic Book)

This is the deterministic foundation pipeline:

Raw Sources
  → Raw Ingest (append-only)
  → Normalize (canonical forms)
  → Semantic Book / Tags / Index
  → Reviewed Vocabulary (tags.db)

Key invariants:

- State progression is attested by **normative decisions**, not inferred from file existence.
- Artifact presence does not imply validity without a decision record.
- Core artifacts MUST fail-fast if missing or unreadable.

Ledger enforcement:

- Each gating transition MUST emit a `decisions` record with ALLOW/DENY.
- Failures MUST emit stop_code + evidence_json.

---

## Flow B -- Agency (ProtoTimmy → Planner → OCP Executor)

Agency is probabilistic in content but deterministic in orchestration:

User Request
  → ProtoTimmy (intent + envelope)
  → Planner Assistant (action family selection)
  → OCP Executor (controlled execution)
  → Response + Attestation

Key invariants:

- Assistants operate only within registered intents/actions.
- Micro-agents (Codex included) are executors, not epistemic authorities.
- Stop conditions (HITL_REQUIRED, CONTRACT_ERROR) MUST be ledger-governed.

UI constraint:

- UI surfaces MUST NOT resume execution via local toggles.
- Resume requires an owned resume_rule and a recorded decision.

---

## Beta 1.0 Forbidden Patterns (Strict)

The following are considered Beta errors:

- UI-only stop/resume handling without ledger attestation
- Soft-fail paths that continue execution after critical errors
- Retrocompatibility shims in core artifact resolution
