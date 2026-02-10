# 08 - Gate Evidence and Retry Contract (SSoT)

**Status:** ACTIVE
**Authority:** Single Source of Truth (SSoT)
**Scope:** normative definition of Gate contracts (Evidence, Skeptic, QA), the evidence model, state predicates, and the retry/resume policy.

The binding between lifecycle, workspace, gate, and Decision Record is defined in instructions/06_promptchain_workspace_mapping.md.

This document formalizes the conditions that allow gates to attest a state without prescribing execution flows.

---

## Foundational principles (Beta 1.0)
- Every state transition produces an append-only Decision Record.
- No gate derives implicit PASS outcomes from logs.
- Logs are evidence, not certificates of truth.
- Without a Decision Record, the transition has not occurred.
- Retry does not equal resume: every retry is a new run with its own attestation.

---

## Decision Record (canonical artifact)
The Decision Record is the only normative artifact emitted by gates.

### Minimal schema
- decision_id (unique, append-only)
-
un_id
- slug
- rom_state
- 	o_state (present only when verdict=PASS)
- erdict (PASS | BLOCK | FAIL | PASS_WITH_CONDITIONS)
- ctor (gatekeeper:<name> | 	immy)
- 	imestamp (UTC)
- evidence_refs[] (references to logs and artifacts)
- stop_code (mandatory when verdict=BLOCK or FAIL)

Logs and files never replace this record.

---

## Persistence in Decision Ledger (normative mapping → SQLite)
The current implementation records decisions inside the decisions table of config/ledger.db.
Normative fields map into ledger columns as follows.

### Verdict mapping
- PASS → ledger ALLOW; 	o_state required.
- PASS_WITH_CONDITIONS → ledger ALLOW; 	o_state and conditions required.
- BLOCK / FAIL → ledger DENY; stop_code required; 	o_state stored as the target reference.

### Field mapping
- gate_name → decisions.gate_name
- rom_state / 	o_state → decisions.from_state / decisions.to_state
- ctor, stop_code, evidence_refs[], conditions → decisions.evidence_json with deterministic keys:
  - ctor
  - stop_code
  - evidence_refs
  - conditions
  -
ormative_verdict
-
ationale → decisions.rationale (deterministic string constructed internally; gates cannot inject free text)

Diagnostics belong to the events table.

### Strictness rules
- PASS and PASS_WITH_CONDITIONS require 	o_state.
- BLOCK and FAIL require stop_code.
- PASS_WITH_CONDITIONS requires non-empty conditions.
- evidence_json must be serialized with ordered keys for determinism.

---

## Evidence Model (log and artifact as evidence)

### General rule
Gates validate verifiable assertions supported by evidence, not raw events.

### Evidence types
- Artifacts: files, directories, databases, QA reports.
- Structured logs: observable, unambiguous, consistent events.
- Context signals: ledger is writable, workspace paths are safe, config is valid.

Missing evidence must be recorded under evidence_gap in the Decision Record.

---

## State predicates (Beta 1.0 normative)

###
aw_ready
The state is attestable only when:
- WorkspaceLayout is valid and complete.
- Canonical directories exist (
aw/, config/, semantic/, ledger).
- config/config.yaml is valid.
- Ledger is writable.

Note: PDF presence does not define the state; PDFs are prerequisites for later actions.

### 	agging_ready
Attested only when:
- semantic/tags.db exists and is coherent.
- 	ags_reviewed.yaml is present (HiTL checkpoint).
- Semantic artifacts align.

This predicate is unique; all implementations must follow its definition.

---

## Evidence Gate - normative contract
The Evidence Gate:
- assesses structural consistency and the presence of evidence;
- never decides advancement;
- always emits a Decision Record.

### Evidence per transition
| Transition | Required evidence |
|------------|------------------|
| WORKSPACE_BOOTSTRAP → SEMANTIC_INGEST | WorkspaceLayout valid, config valid, ledger writable |
| SEMANTIC_INGEST → FRONTMATTER_ENRICH | semantic/tags.db, 	ags_reviewed.yaml |
| FRONTMATTER_ENRICH → VISUALIZATION_REFRESH | draft markdown and semantic mapping |
| VISUALIZATION_REFRESH → PREVIEW_READY | knowledge graph and preview artifacts |
| PREVIEW_READY → COMPLETE | final artifacts ready |

---

## Retry / Resume contract (Beta 1.0)

### Core rule
Every retry is a new run.
No silent retries, implicit resumes, or continuations of the same execution.

### Allowed retry conditions
- Existing artifacts remain intact.
- No structural violation (layout, config, scope).
- A new
un_id and Decision Record are created.

### Retry blocked when
- WorkspaceLayoutInvalid
- WorkspaceNotFound
- Persistent ConfigError

In such cases: verdict=BLOCK, stop_code=HITL_REQUIRED; the decision escalates to Timmy (HiTL).

---

## QA Gate → COMPLETE
- The QA Gate is necessary but not sufficient for pipeline completion.
- Minimum QA requirements:
  1. pre-commit run --all-files → PASS
  2. pre-commit run --hook-stage pre-push --all-files → PASS
  3. QA reports available as evidence
- logs/qa_passed.json is the core-gate artifact.
- 	imestamp is telemetry and must not influence deterministic comparisons of core artifacts.
- On FAIL: verdict=BLOCK, stop_code=QA_GATE_FAILED

Only after:
1. QA Gate emits a PASS Decision Record
2. Evidence and Skeptic Gate confirm final coherence
3. Timmy/Gatekeeper attest COMPLETE

The transition to COMPLETE is itself a Decision Record.

---

## Non-goals
- Introduce no new states.
- Define implementation or logging details.
- Automate decisions: gates attest, they do not execute.
