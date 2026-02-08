# 09 - Context/Layout Contract (1.0 Beta, closed envelope)

**Status:** FROZEN (final for 1.0 Beta)
**Scope:** normative contract for Context/Layout and workspace path derivation
**Authority:** this document is binding and adds no HOW/implementation guidance

## Purpose
Define the definitive Context/Layout contract for Beta 1.0: only one perimeter is valid, silent fallbacks are prohibited, and fail-fast behavior is mandatory.

## Minimal Definitions
- **context**: runtime context object (slug, repo_root_dir, config) used to build the layout.
- **WorkspaceLayout**: structure exposing the canonical workspace paths for a client.
- **repo_root_dir**: repository root; it is a required contract input.
- **book_dir**: canonical Knowledge Book directory (normalized markdown) produced by the Epistemic Envelope.

## 1) Single Source of Truth (SSoT)
- `WorkspaceLayout.from_context(context)` MUST be the sole source of truth for canonical paths.
- Every runtime path MUST derive from the resulting `WorkspaceLayout`.

## 2) `repo_root_dir` (mandatory, no alias)
- `repo_root_dir` MUST always be present.
- `repo_root_dir` MUST NOT be derived from CWD, environment heuristics, directory climbing, or “convenience” values.
- `base_dir` is FORBIDDEN as an alias or alternative to derive or substitute `repo_root_dir`.
- `md_dir` is FORBIDDEN as an alias or alternative to derive or substitute `book_dir`.

### 2.1 `WORKSPACE_ROOT_DIR` and the `<slug>` macro
Multi-workspace deployments MAY document `WORKSPACE_ROOT_DIR` using the placeholder `<slug>` (e.g., `.../timmy-kb-<slug>`), but:

- the macro MUST be resolved centrally by `ClientContext` before any validation;
- the resolution MUST be deterministic and MUST NOT introduce alternative fallbacks or distributed heuristics;
- downstream tools MUST NOT re-substitute `<slug>`; they MUST consume the root already resolved by the context;
- documentation SHALL note that `WORKSPACE_ROOT_DIR` may contain `<slug>`, but the runtime layer MUST NOT consume `<slug>` directly: it passes through the context.

The macro is resolved exactly once, before building the `WorkspaceLayout`, and is part of the contract (it is not a silent recovery behavior).

## 3) Derived paths (layout-first)
- `raw_dir`, `book_dir`, `semantic_dir`, `logs_dir`, and `config_dir` MUST be obtained from the `WorkspaceLayout`.
- Consumers (UI/CLI/runtime services/tools) MUST NOT:
  - read `context.*_dir` entries (if present),
  - rebuild paths by concatenating strings,
  - compute “equivalent” paths outside the layout.

Permitted minimal example (illustrative only):
```
layout = WorkspaceLayout.from_context(context)
raw_dir = layout.raw_dir
book_dir = layout.book_dir
```

## 4) Explicit prohibitions (forbidden patterns)
The following patterns are FORBIDDEN when they touch critical contract fields or paths:

### 4.1 `getattr` with a default
```
getattr(context, "repo_root_dir", None)
getattr(context, "raw_dir", default)
```

### 4.2 OR-chain / implicit defaulting
```
repo_root = context.repo_root_dir or Path.cwd()
raw_dir = context.raw_dir or (repo_root / "output" / slug / "raw")
```

### 4.3 absorbing `try/except` (error masking)
```
try:
    layout = WorkspaceLayout.from_context(context)
except Exception:
    layout = WorkspaceLayout.from_defaults(...)
```

### 4.4 silent defaults on mandatory fields/dirs
Any behavior that “continues” without `repo_root_dir` or without a valid layout is FORBIDDEN.

## 5) Error policy (fail-fast, noisy, explicit)
- Every violation of this contract MUST be treated as a **contractual error**.
- The error MUST be **fail-fast**, **noisy** (explicit log/event), and **not implicitly recovered**.
- No implicit recovery is allowed: there MUST NOT exist “auto-fix” routines or automatic fallbacks that switch to an alternative path.

## 6) Critical distinction: HiTL checkpoint ≠ fallback
- A **HiTL checkpoint** is a governed STOP: it blocks progress until the human decision/artifact prescribed by the contract becomes available.
- A **fallback** is an alternative path that continues without an explicit decision; it is FORBIDDEN inside the Beta perimeter.
- HiTL checkpoints MUST be explicit, traceable, and unambiguous; they are not contract alternatives but conditions to continue within the envelope.

## 7) Beta perimeter (critical runtime)
- The Beta critical runtime recognizes **a single Context/Layout contract**: the one defined in this document.
- Dev-only tools or experiments MAY exist only outside the critical runtime and MUST NOT introduce multiple contracts (no alternative derived paths, no silent fallbacks).
