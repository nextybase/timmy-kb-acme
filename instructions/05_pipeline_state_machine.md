# Pipeline State Machine - v1.0 (Beta)

## Scope & Non-goals
- Defines the **normative pipeline state machine** governing artefact readiness up to the production of:
  - semantically enriched markdown,
  - validated knowledge graph (KG).
- This document is **authoritative** for pipeline states and transitions.
- **Non-goals**:
  - implementation details,
  - CLI commands,
  - UI flow descriptions,
  - performance or optimization concerns.

---

## Agency & Lifecycle Relationship
- Pipeline completion (enriched markdown + validated KG) is the **only admissible condition**
  for transitioning agency from **ProtoTimmy** to **Timmy**.
- Lifecycle phases
  (`PLANNING → MICRO_PLANNING → VALIDATION → EXECUTION → QA → CLOSURE`)
  orchestrate **decision flow**.
- Pipeline states track **artefact readiness**, not decisions.
- A pipeline state **never advances implicitly**:
  progression requires an explicit **Decision Record** emitted by Gatekeepers or Timmy.

---

## Normative Invariants (Beta 1.0)
- Pipeline states are **attested**, not deduced.
- Every state transition produces a **Decision Record (append-only)**:
  `PASS | BLOCK | FAIL | PASS_WITH_CONDITIONS`.
- Artefact existence alone **never** advances the pipeline.
- Allowed action families **do not imply** permission to advance state.
- State regression is **forbidden**:
  failures produce new Decision Records; the current state remains unchanged.
- Retry always means **new run, new record**, never rollback.

---

## Pipeline States

| State | Entry Condition (normative) | Required Artefacts (evidence) | Allowed Actions (family) | Exit Condition |
|------|-----------------------------|--------------------------------|--------------------------|----------------|
| `WORKSPACE_BOOTSTRAP` | Intent registered; workspace slug resolved | Workspace layout created via `WorkspaceLayout` (`raw/`, `config/`, `semantic/`, ledger) | `REGISTER_*`, `VALIDATE_*` (layout, config, ledger) | Gatekeepers attest workspace integrity → `SEMANTIC_INGEST` |
| `SEMANTIC_INGEST` | Workspace integrity attested | Raw PDFs present, `config/config.yaml` | `VALIDATE_*`, `GENERATE_*` (semantic extraction, indexing) | Semantic Gatekeepers attest `tags.db` validity → `FRONTMATTER_ENRICH` |
| `FRONTMATTER_ENRICH` | Semantic layer attested | Draft frontmatter (`book/*.md`), draft `README.md`, `SUMMARY.md` | `VALIDATE_*` (frontmatter, semantic coherence) | Gatekeepers attest frontmatter correctness → `VISUALIZATION_REFRESH` |
| `VISUALIZATION_REFRESH` | Frontmatter attested | Preview artefacts (`semantic/kg.tags.*`, final README/SUMMARY drafts) | `GENERATE_*` (visual previews, vision mappings) | Gatekeepers/OCP attest KG + preview → `PREVIEW_READY` |
| `PREVIEW_READY` | Preview artefacts attested | Final `book/` + `semantic/` artefacts | `VALIDATE_*` (final QA checks) | On PASS: pipeline eligible for completion |

**Normative note**
- `COMPLETE` is **not a pipeline state**.
- It is a **closure act**, attested via a Decision Record, once all requirements are satisfied.

---

## State Transitions (Normative)
- `WORKSPACE_BOOTSTRAP → SEMANTIC_INGEST`
  Triggered **only** by a Decision Record confirming workspace integrity.
- `SEMANTIC_INGEST → FRONTMATTER_ENRICH`
  Requires Decision Record confirming `semantic/tags.db` validity.
- `FRONTMATTER_ENRICH → VISUALIZATION_REFRESH`
  Requires Decision Record confirming draft markdown + semantic consistency.
- `VISUALIZATION_REFRESH → PREVIEW_READY`
  Requires Decision Record confirming preview artefacts and KG alignment.
- `PREVIEW_READY → COMPLETE`
  Closure Decision Record emitted once enriched markdown **and** validated KG are attested.

---

## Stop Conditions & Resume Rules
All stops produce a **Decision Record** and do **not** modify the current state.

| Stop Condition | Owner | stop_code | Required Action | Resume Rule |
|---------------|------|-----------|-----------------|-------------|
| `malformed_artifact` | Domain Gatekeeper | `ContractError` | Regenerate invalid artefacts | New run from same state |
| `missing_inputs` | Domain Gatekeeper | `ContractError` | Supply missing artefacts | New run from same state |
| `unsupported_action` | Gatekeeper / OCP | `HITL_REQUIRED` | Revise Work Order | Resume after explicit approval |
| `hitl_block` | OCP / Timmy | `HITL_REQUIRED` | Human decision via Timmy | Resume from same state |
| `invariant_violation` | Gatekeeper / Timmy | `PolicyViolation` | Correct design/config mismatch | New run only after correction |

---

## Agency Switch Invariant
- Until pipeline completion is **attested**, ProtoTimmy retains full agency.
- After completion:
  - Timmy assumes agency,
  - Gatekeepers and OCP **continue** to enforce stops and validation.
- Agency transition is itself a **Decision Record**.

---

## Anti-confusion Rules
- **Pipeline ≠ Prompt Chain**
  Pipeline tracks artefact readiness; Prompt Chain governs reasoning and decisions.
- **Pipeline state ≠ lifecycle phase**
  A state may span multiple lifecycle phases.
- **Artefact readiness ≠ approval**
  Only Gatekeepers or Timmy can attest progress.

---

## Completion Checklist (normative)
- [ ] Workspace layout created and attested (`WORKSPACE_BOOTSTRAP`).
- [ ] Semantic artefacts validated and attested (`SEMANTIC_INGEST`).
- [ ] Frontmatter drafts validated (`FRONTMATTER_ENRICH`).
- [ ] Preview and KG artefacts validated (`VISUALIZATION_REFRESH`).
- [ ] Enriched markdown + validated KG attested.
- [ ] Closure Decision Record emitted (`COMPLETE`).
- [ ] Agency transition ProtoTimmy → Timmy recorded.
