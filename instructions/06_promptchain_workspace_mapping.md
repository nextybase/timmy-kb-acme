# Prompt Chain ↔ Workspace Mapping (SSoT Binding)

**Status:** ACTIVE
**Authority:** Single Source of Truth (SSoT)
**Scope:** normative binding between the Prompt Chain lifecycle, workspace states, gate requirements, and Decision Records.

This document **does not introduce new semantics**:
- it binds and harmonizes definitions already available in the source documents.

Normative references:
- instructions/02_prompt_chain_lifecycle.md – lifecycle and action families
- instructions/05_pipeline_state_machine.md – workspace states
- instructions/07_gate_checklists.md – gate operational checklists
- instructions/08_gate_evidence_and_retry_contract.md – Evidence/QA/Skeptic Gate

In case of conflict, **this document prevails** as the SSoT binding.

---

## Defines vs References

### Defines
- Mapping **lifecycle phase ↔ workspace state**.
- **Mandatory** gate requirements for each transition.
- **Gate → Decision Record** constraint (append-only).
- Minimal bridge fields correlating lifecycle, workspace, and gate contexts.

### References
- Semantics of lifecycle phases.
- Semantics of workspace states.
- Internal gate rules.
- Retry and stop policies.

---

## Out of Scope
- Introducing new states, phases, or gates.
- Modifying action families.
- Defining implementation, logging, or tooling.
- Introducing alternative events or semantic shortcuts.

---

## Lifecycle phases ↔ Workspace states ↔ Allowed action families

References:
- instructions/02_prompt_chain_lifecycle.md
- instructions/05_pipeline_state_machine.md

| Lifecycle phase | Allowed workspace state(s) | Allowed action families |
|-----------------|----------------------------|--------------------------|
| PLANNING | WORKSPACE_BOOTSTRAP | REGISTER_* |
| MICRO_PLANNING | WORKSPACE_BOOTSTRAP | Work Order Envelope definition |
| VALIDATION | SEMANTIC_INGEST, FRONTMATTER_ENRICH | VALIDATE_* |
| EXECUTION | FRONTMATTER_ENRICH, VISUALIZATION_REFRESH | GENERATE_*, EXECUTE_* |
| QA | VISUALIZATION_REFRESH, PREVIEW_READY | VALIDATE_* |
| CLOSURE | PREVIEW_READY | summary logging / closure |

**Normative note**
- Lifecycle phases **do not advance** the workspace state.
- Lifecycle phases govern the *decision process*, not the attestation.

---

## Gate requirements per workspace transition

References:
- instructions/07_gate_checklists.md
- instructions/08_gate_evidence_and_retry_contract.md

| Workspace transition | Mandatory gates |
|---------------------|-----------------|
| WORKSPACE_BOOTSTRAP ↔ SEMANTIC_INGEST | Evidence Gate + Skeptic Gate |
| SEMANTIC_INGEST ↔ FRONTMATTER_ENRICH | Evidence Gate + Skeptic Gate |
| FRONTMATTER_ENRICH ↔ VISUALIZATION_REFRESH | Evidence Gate + Skeptic Gate |
| VISUALIZATION_REFRESH ↔ PREVIEW_READY | Evidence Gate + Skeptic Gate |
| PREVIEW_READY ↔ COMPLETE | QA Gate + Evidence Gate + Skeptic Gate |

No transition is valid if **any** required gate fails to issue a verdict.

---

## Gate → Decision Record binding (Beta 1.0)

Reference:
- instructions/08_gate_evidence_and_retry_contract.md

### Core rule
**Every state transition always produces an append-only Decision Record.**

| Gate | Allowed verdicts | Normative output |
|-----|-----------------|------------------|
| Evidence Gate | PASS, BLOCK, FAIL | Decision Record |
| Skeptic Gate | PASS, PASS_WITH_CONDITIONS, BLOCK | Decision Record |
| QA Gate | PASS, FAIL, RETRY | Decision Record |

Specific events (*_blocked, *_retry, etc.) may exist as **logs or telemetry**, but they **never replace** the Decision Record.

---

## Bridge fields (lifecycle ↔ workspace ↔ gate)

References:
- instructions/04_microagents_work_orders.md
- docs/observability.md
- system/ops/runbook_codex.md

| Field | Mandatory? | Normative note |
|------|----------|----------------|
|
un_id | always | Unique run identifier |
| slug | always | Workspace identifier |
| phase_id | always | Current lifecycle phase |
| state_id | always | Current workspace state |
| intent_id | always | Intent/Action registry |
| ction_id | always | Executed action |
| decision_id | always | Decision Record identifier |
| 	race_id | if OTEL active | Mandatory when OTEL is enabled |
| span_id | if OTEL active | Mandatory when OTEL is enabled |

---

## Anti-confusion invariants
- **Lifecycle ≠ Pipeline**
  Lifecycle governs *reasoning*; pipeline governs *state*.
- **Artifact readiness ≠ state**
  Artifacts are evidence, not decisions.
- **Gate ≠ automation**
  Gates issue verdicts, not implicit transitions.
- **Decision Record = truth**
  No Decision Record implies the transition **has not occurred**.
