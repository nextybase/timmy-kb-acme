# 10_runtime_strict_contract_beta.md

Status: ACTIVE (Beta 1.0)
Authority: OCP / C-Board
Scope: Runtime execution, Semantic pipeline, Vision provisioning, Onboarding flows
Applies to: All Beta 1.0 executions

---

## 1. Contract Vision

The system MUST operate in **deterministic, strict-only mode**.

Execution SHALL be allowed **only** when all structural and semantic prerequisites are present and verifiable.
Any deviation from declared formats, schemas, or invariants MUST result in a **deterministic hard-fail**.

The system MUST NOT introduce:
- silent fallbacks
- best-effort parsing
- auto-generated structure
- tolerance-based recovery paths

Determinism takes precedence over usability, resilience, or graceful degradation.

---

## 2. System Invariants

**I-1 -- Strict-only execution**
The system MUST be strict-only.
No operational path may accept outputs that are not compliant with declared schemas.

**I-2 -- Deterministic fail-fast**
Any error on prerequisites or output validity MUST interrupt execution with:
- an explicit error
- a stable, reproducible message

**I-3 -- No silent fallback**
The system MUST NOT continue execution in best-effort or log-only mode after a critical error.

**I-4 -- Binding Ledger**
Decision Records (ledger) are binding.
Any failure to write or validate a Decision Record MUST block state advancement.

**I-5 -- Deterministic NLP semantics**
If the required NLP backend is `spacy`:
- SpaCy errors MUST cause hard-fail
- missing or empty `tags.db` MUST cause hard-fail

**I-6 -- Input-derived structure only**
Proposed structures MUST derive strictly from input evidence.
Placeholders, auto-branches, or inferred nodes MUST NOT be introduced.

**I-7 -- Pure Vision output**
Vision output MUST be **pure JSON**.
Code fences, prefixes, suffixes, or tolerant parsing MUST NOT be accepted.

**I-8 -- Goal format invariant**
The `Goal N` format MUST be present and parsable.
Its absence MUST cause hard-fail.

---

## 3. Input Validity Rules

**3.1 -- Vision Statement**
Required sections MUST be present and non-empty.
Missing or empty sections invalidate the input.

**3.2 -- Vision payload**
The payload MUST comply with `VisionOutput` schema.
`areas` MUST be a non-empty list within the allowed range.

**3.3 -- Canonical vocabulary**
When vocab or terms are required:
- `tags.db` MUST exist
- `tags.db` MUST be readable

**3.4 -- NLP backend availability**
If `TAGS_NLP_BACKEND == "spacy"`, the SpaCy model MUST be available and loadable.

**3.5 -- Area documents**
Each Vision area MUST provide a non-empty `documents` list for raw folder construction.

**3.6 -- System folders**
`identity` and `glossario` folders are valid ONLY if explicitly present in the payload.
They MUST NOT be auto-added.

---

## 4. Output Validity Rules

**4.1 -- Vision output format**
Vision output MUST be valid pure JSON.
Any non-JSON content MUST be rejected.

**4.2 -- Schema compliance**
Vision output MUST comply with `VisionOutput` schema in strict mode.

**4.3 -- Layout proposals**
Layout proposals MUST NOT contain placeholders.
All nodes MUST derive from actual input tokens.

**4.4 -- Structural merge**
Structural merge conflicts MUST cause hard-fail.
Alternative or suffixed keys MUST NOT be generated.

---

## 5. Mandatory Hard-Fail Conditions

The system MUST hard-fail in the following cases:

- `strict_output` is not `True`
- Vision LLM output contains code fences or extra text
- Goal parsing without valid `Goal N` blocks
- Missing, empty, or unreadable `tags.db` when required
- `TAGS_NLP_BACKEND == "spacy"` and SpaCy is unavailable or errors
- Failure of `doc_entities` enrichment when invoked
- Insufficient structure for `min_children`
- Structural merge conflicts
- Ledger write or validation failure

---

## 6. Explicitly Out of Scope for Beta 1.0

The following are NOT guaranteed and MUST NOT be implemented:

- Tolerance for incomplete or malformed input
- Automatic repair of LLM output
- Non-strict or schema-less execution modes
- Auto-generation of structural elements (placeholders, alt-keys)
- Any non-deterministic or fallback-dependent behavior

---

## 7. Normative Glossary

**Deterministic**
Given identical input and configuration, the system MUST either:
- produce the same output, or
- fail with the same error.

**Strict-only**
Only schema-compliant output is accepted.
Any deviation MUST cause hard-fail.

**Fallback**
Alternative behavior triggered by missing or invalid input.
In Beta 1.0, fallbacks MUST NOT alter structure or semantics.

**Best-effort**
Tolerant parsing or recovery attempts.
In Beta 1.0, best-effort is forbidden on structured output.

**Hard-fail**
Immediate and explicit termination with deterministic error.

**SSoT (Single Source of Truth)**
A single authoritative source (e.g. `tags.db` for canonical vocabulary).

**Binding Ledger**
State advancement is allowed ONLY after a successful Decision Record.

---

End of document.
