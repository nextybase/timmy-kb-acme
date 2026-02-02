# 10_runtime_strict_contract_beta.md

Status: ACTIVE (Beta 1.0)
Authority: OCP / C-Board
Scope: Runtime execution, Semantic pipeline, Vision provisioning, Onboarding and tooling flows
Applies to: All Beta 1.0 executions

---

## 1. Contract Vision

The system operates in **strict-first mode**.

Strict execution is the **default and normative runtime behavior**.
All runtime decisions, state transitions, and canonical artefacts are governed by strict rules unless an **explicit, documented, and capability-gated exception** authorizes an alternative path.

Execution SHALL proceed **only** when all declared structural, semantic, and environmental prerequisites are present and verifiable.
Any deviation from declared formats, schemas, or invariants MUST result in a **deterministic hard-fail**.

The system MUST NOT introduce:
- silent fallbacks;
- best-effort parsing;
- auto-generated structure;
- tolerance-based recovery paths.

**Non-strict execution paths are not degradations**.
They exist solely as **documented exceptions**, activated through explicit capability gates, and MUST:
- be observable and traceable;
- preserve determinism;
- never alter runtime semantics silently.

Determinism takes precedence over usability, resilience, or graceful degradation, except where a verified capability gate explicitly authorizes a controlled semantic variation.

---

## 2. System Invariants

**I-1 — Strict-first execution**
Strict execution is the default runtime behavior.
No operational path may accept outputs that are not compliant with declared schemas unless a documented capability gate explicitly authorizes a non-strict exception.

**I-2 — Deterministic fail-fast**
Any error on prerequisites or output validity MUST interrupt execution with:
- an explicit error;
- a stable, reproducible message.

**I-3 — No silent fallback**
The system MUST NOT continue execution in best-effort or log-only mode after a critical error.

**I-3bis — Capability-gated exceptions**
The runtime core preserves strict behavior by default.
Non-strict paths are permitted **only** when:
- the capability is explicitly declared and documented;
- prerequisites are verifiable;
- the semantic deviation is observable and traceable.

Any heuristic, fallback, partial execution, or tolerance-based recovery is forbidden in the runtime core unless explicitly authorized by a capability gate.

**I-4 — Binding Ledger**
Decision Records (ledger) are binding.
Any failure to write or validate a Decision Record MUST block state advancement.

**I-5 — Deterministic NLP semantics**
If the required NLP backend is `spacy`:
- SpaCy errors MUST cause hard-fail;
- missing or empty `tags.db` MUST cause hard-fail.

**I-6 — Input-derived structure only**
Proposed structures MUST derive strictly from input evidence.
Placeholders, auto-branches, or inferred nodes MUST NOT be introduced.

**I-7 — Pure Vision output**
Vision output MUST be **pure JSON**.
Code fences, prefixes, suffixes, or tolerant parsing MUST NOT be accepted.

**I-8 — Goal format invariant**
The `Goal N` format MUST be present and parsable.
Its absence MUST cause hard-fail.

**I-9 — Normative Ledger is non-diagnostic**
Decision Records are **normative** and MUST remain **low-entropy**.

Allowed in Decision Records:
- stable `stop_code` values (required for BLOCK / FAIL);
- stable `actor` identifiers;
- stable `gate_name`, `from_state`, `to_state`;
- deterministic `evidence_refs[]`;
- deterministic `reason_code` or `rationale` labels.

Forbidden in Decision Records:
- exception strings or summaries;
- stack traces;
- environment-dependent diagnostics;
- non-deterministic free text.

Diagnostic details MUST be emitted only via structured logs or events.

---

## 2bis. Capabilities (Core vs Optional Integrations)

The architecture distinguishes a deterministic **runtime core** from **capability-gated integrations**.

| Capability | Scope | Fail-fast rule |
|---|---|---|
| Deterministic core (pipeline, workspace layout, gating, ledger) | Runtime core | Strict / fail-fast |
| Optional integrations (e.g. Google Drive) | Capability-gated | Explicit prerequisite failure |

Optional adapter prerequisites (Drive):
- extras `.[drive]`, `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`;
- missing prerequisites MUST raise an explicit capability error;
- `--dry-run` and local-only modes are first-class and do not depend on Drive.

---

## 2ter. Runtime vs Tooling Boundary (Beta 1.0)

The system enforces a strict boundary between **runtime execution** and **supporting tooling**.

**Runtime core:**
- executes state transitions;
- produces canonical artefacts;
- records Decision Records;
- enforces invariants and schemas;
- fails fast on any missing prerequisite.

**Tooling and onboarding flows (out of runtime scope):**
- environment validation and provisioning;
- workspace bootstrap and migration;
- diagnostic and administrative utilities;
- controlled generation of scaffolding artefacts.

Tooling MAY perform bootstrap operations but:
- MUST NOT advance runtime state;
- MUST NOT bypass runtime invariants;
- MUST NOT generate Decision Records unless explicitly specified by a gate.

---

## 2quater. Bootstrap Authorization

Bootstrap behavior is **forbidden in the runtime core**.

Bootstrap operations are permitted **only** within onboarding or tooling flows and require an **explicit authorization gate**.

An explicit authorization signal (e.g. `TIMMY_ALLOW_BOOTSTRAP=1`) indicates:
- informed consent to perform bootstrap actions;
- execution outside the runtime core;
- absence of implicit fallback or degradation.

Bootstrap authorization is **not a preference** and **not a runtime mode**.
It is a safety gate that prevents accidental or implicit mutation of runtime workspaces.

---

## 3. Input Validity Rules

**3.1 — Vision Statement**
Required sections MUST be present and non-empty.

**3.2 — Vision payload**
The payload MUST comply with the `VisionOutput` schema.
`areas` MUST be a non-empty list within the allowed range.

**3.3 — Canonical vocabulary**
When vocabulary is required:
- `tags.db` MUST exist;
- `tags.db` MUST be readable.

**3.4 — NLP backend availability**
If `TAGS_NLP_BACKEND == "spacy"`, the SpaCy model MUST be available and loadable.

**3.5 — Area documents**
Each Vision area MUST provide a non-empty `documents` list.

**3.6 — System folders**
`identity` and `glossario` folders are valid ONLY if explicitly present in the payload.

---

## 4. Output Validity Rules

**4.1 — Vision output format**
Vision output MUST be valid pure JSON.

**4.2 — Schema compliance**
Vision output MUST comply with the `VisionOutput` schema in strict execution.

**4.3 — Layout proposals**
Layout proposals MUST NOT contain placeholders.

**4.4 — Structural merge**
Structural merge conflicts MUST cause hard-fail.

---

## 5. Mandatory Hard-Fail Conditions

The system MUST hard-fail in the following cases:

- `strict_output` is not `True`;
- Vision output contains non-JSON content;
- invalid or missing `Goal N` blocks;
- execution with missing configuration or unavailable required capability;
- missing or unreadable `tags.db` when required;
- SpaCy errors when selected;
- structural conflicts or insufficient hierarchy;
- ledger write or validation failure.

---

## 6. Explicitly Out of Scope for Beta 1.0

The following are NOT supported:

- tolerance for malformed input;
- automatic repair of model output;
- implicit non-strict execution;
- auto-generation of structure;
- silent or heuristic fallback behavior.

---

## 7. Operational Definitions

**Strict-first**
Default runtime behavior enforcing schema and invariants.

**Non-strict**
A documented, capability-gated exception that alters semantics explicitly and observably.

**Degradation**
Any silent fallback or best-effort behavior not authorized by a capability gate.

**Capability-gated**
A named feature requiring explicit prerequisites and authorization.

**Hard-fail**
Immediate deterministic termination.

**SSoT**
Single Source of Truth.

**Binding Ledger**
State advancement occurs only after a valid Decision Record.

---

End of document.
