Agency & Orchestration Model - v1.0 - Prompt Chain Lifecycle

## Scope and perimeter
- This document outlines the Prompt Chain timeline from a linear narrative perspective.
- The canonical pipeline state machine and all valid transitions are specified in `instructions/05_pipeline_state_machine.md` (SSoT).
- Timeline and state machine are complementary: the timeline shows who does what and when; the state machine records formal states and permitted transitions.

## Canonical Prompt Chain Phases (Timeline)

### PLANNING
- **Goal:** collect user intents and identify relevant Domain Gatekeepers.
- **Output required:** an operational plan with registered intents, Gatekeeper coverage, and annotated implicit HiTLs.
- **Allowed actions:** policy analysis, AGENTS consultation, drafting preliminary REGISTER_INTENT/REGISTER_ACTION entries.
- **Forbidden actions:** direct executions, HiTL bypass, assigning or invoking micro-agents.
- **Actors involved:** Timmy/ProtoTimmy (decides); Domain Gatekeepers (advise constraints, influence coverage, signal limits); micro-agents do not participate.

### MICRO_PLANNING
- **Goal:** detail sub-prompts and assign micro-agents for each registered Action.
- **Output required:** an ordered micro-task list (Work Order Envelope) and Action templates with validated families.
- **Allowed actions:** prompt assembly, micro-agent assignment, Gatekeeper coverage review.
- **Forbidden actions:** executions, registering new Actions without HiTL, out-of-sequence changes.
- **Actors involved:**
  - Timmy/ProtoTimmy (coordinates and assigns micro-agents; sole authorized actor).
  - Engineering Gatekeeper/OCP and Domain Gatekeepers (provide constraints and signal limits; they do not select agents).
- **Operational note:** modifications to micro-agent assignments after this phase require explicit HiTL (e.g., REGISTER_INTENT, REGISTER_ACTION, stop_code == "HITL_REQUIRED").

### VALIDATION
- **Goal:** ensure prompts and Actions respect policies and guardrails (semantic, compliance, gate).
- **Output required:** formal validation (StructuredResult OK) or HiTL block.
- **Allowed actions:** invoke VALIDATE_* Actions, check HiTL triggers, log stops.
- **Forbidden actions:** run GENERATE_*/EXECUTE_* before validation or bypass gates.
- **Actors involved:**
  - Domain Gatekeepers (assess evidence, validate schema/guardrails, issue verdicts).
  - Engineering Gatekeeper/OCP (control plane applying Skeptic, Entrypoint, HiTL gates).
  - Micro-agent (executes technical VALIDATE_* checks under the Work Order Envelope and returns StructuredResult; no decision role).
  - Timmy/ProtoTimmy (records verdicts and coordinates HiTL).
- **Note:** preceding GENERATE_* or EXECUTE_* Actions may require additional validation; such checks remain inside VALIDATION and finish before QA.

### EXECUTION
- **Goal:** execute permitted Actions (GENERATE_*, EXECUTE_*) via micro-agents.
- **Output required:** generated artifacts or documented side effects plus StructuredResult.
- **Allowed actions:** registered GENERATE_* and EXECUTE_* entries with logged side effects.
- **Forbidden actions:** register new intents/actions or execute absent registry approval.
- **Actors involved:** micro-agents execute; Gatekeepers observe; Engineering Gatekeeper/OCP coordinates control plane; Timmy monitors.

### QA
- **Goal:** verify artifacts, logs, and HiTL compliance before closure.
- **Output required:** QA report, possible reopenings, or stop_code.
- **Allowed actions:** VALIDATE_* on artifacts, cspell/test checks, re-exposure decisions.
- **Forbidden actions:** new executions without a new phase or ignoring guardrails.
- **Actors involved:** Domain Gatekeepers evaluate; Engineering Gatekeeper/OCP applies gates; Timmy approves; micro-agent may execute VALIDATE_* for QA scope.

### CLOSURE
- **Goal:** archive the Prompt Chain, update evidence, and notify the user.
- **Output required:** summary, closure logs, and HiTL evidence.
- **Allowed actions:** record keeping, message_for_ocp notifications, closing the phase.
- **Forbidden actions:** fresh executions or coverage changes without HiTL.
- **Actors involved:** Timmy closes; Domain Gatekeepers confirm; micro-agents do not participate.

## Global linearity rules
- Advance only when the previous phase's required output is available and validated.
- Returning to an earlier phase requires explicit actions (e.g., updated REGISTER_INTENT) and confirmed HiTL.

## Controlled local recursion
- Loops stay within the same phase and occur at orchestration level (e.g., Engineering Gatekeeper re-invoking micro-agents during EXECUTION) without altering the global timeline.
- Micro-agents maintain no state or dialogue: each iteration is a fresh invocation under the Work Order Envelope.
- Recursion refines prompts or validations without switching the main phase.

## Predefined HiTL triggers
- Mandatory when: REGISTER_INTENT, REGISTER_ACTION registrations; coverage updates; stop_code == "HITL_REQUIRED".
- Each phase documents triggers and stopping behavior via message_for_ocp.

## Phase-scoped Allowed Actions
- PLANNING: REGISTER_INTENT, REGISTER_ACTION.
- MICRO_PLANNING: define the Work Order Envelope and assign micro-agents.
- VALIDATION: VALIDATE_* (schema, guardrails).
- EXECUTION: GENERATE_*, EXECUTE_*.
- QA: VALIDATE_* (reports, cspell), possible NEED_INPUT.
- CLOSURE: summary logging and HiTL confirmation.
- No action outside its phase is valid.

## State Machine (Option B) - Transition Table
| STATE | EVENT | GUARD | ACTIONS ALLOWED | OUTPUT/ARTIFACTS | NEXT_STATE | NOTES |
| --- | --- | --- | --- | --- | --- | --- |
| PHASE_PLANNING | INTENT_REGISTERED | intent and coverage documented, HiTL annotated, allowed_actions defined | REGISTER_INTENT, REGISTER_ACTION preliminaries | updated intent registry, coverage file | PHASE_MICRO_PLANNING | legacy message_for_ocp records the transition |
| PHASE_MICRO_PLANNING | ACTION_REGISTERED | complete Work Order Envelope, micro-agents assigned under coverage | micro-agent assignment, prompt definition | task list, Work Order documents | PHASE_VALIDATION | new assignments require HiTL (REGISTER_* or stop_code == "HITL_REQUIRED") |
| PHASE_VALIDATION | VALIDATION_OK | VALIDATE_* family, guardrails passed, no active EXECUTE/GENERATE | VALIDATE_* under Work Order Envelope | StructuredResult OK, logs | PHASE_EXECUTION | Control Plane applies Skeptic/Entrypoint gates |
| PHASE_VALIDATION | VALIDATION_FAIL | negative evidence, stop_code/HiTL, coverage mismatch | suspension and logging | stop_code, error log | PHASE_VALIDATION | Domain Gatekeepers release verdict and coordinate HiTL |
| PHASE_EXECUTION | EXECUTION_OK | registered GENERATE_*/EXECUTE_*, instructions/ verified | GENERATE_*/EXECUTE_* with tracked side effects | artifacts, StructuredResult | PHASE_QA | instructions/ folder checked before operational prompts |
| PHASE_EXECUTION | EXECUTION_FAIL | runtime errors or guardrail violations | block and HiTL trigger | stop_code, evidence | PHASE_VALIDATION | recall Domain Gatekeepers for validation |
| PHASE_QA | QA_OK | QA VALIDATE_* completed with positive StructuredResult | QA VALIDATE_* scope | QA report, cspell log | PHASE_CLOSURE |
| PHASE_QA | QA_FAIL | QA mismatch, HiTL required | additional VALIDATE_* requests | issue log | PHASE_EXECUTION | micro-agent returns NEED_INPUT |
| PHASE_CLOSURE | CLOSURE_CONFIRMED | summary and HiTL evidence recorded | closure log, message_for_ocp | PHASE_FINAL | final log with HiTL evidence |
| PHASE_FINAL | HITL_REQUIRED | persistent stop_code == "HITL_REQUIRED" | no new actions | report with message_for_ocp | PHASE_PLANNING | requires human intervention to resume |

## Example walkthrough
- Scenario: producing documentation under instructions/.
- Sequence: MICRO_PLANNING (define GENERATE_* Action), EXECUTION (micro-agent produces files), QA (VALIDATE_* the content), CLOSURE (summaries).
- Mandatory rule: every operational prompt verifies instructions/ before acting to avoid divergence.

## Appendix - Stop & HiTL (Mini-C)
- stop_conditions:
  - HITL_REQUIRED:
      trigger: stop_code == "HITL_REQUIRED" or _CODEX_HITL_KEY set after invalidations.
      owner: Domain Gatekeepers (Semantic/Compliance) and Engineering Gatekeeper/OCP.
      required_human_action: HiTL supervision with message_for_ocp and acknowledgement.
      resume_rule: resumes in PHASE_VALIDATION or PHASE_EXECUTION after human confirmation.
      resume_phase: SAME
  - SKEPTIC_GATE:
      trigger: Skeptic Gate activated by guardrails.
      owner: Engineering Gatekeeper/OCP.
      required_human_action: documented acknowledgement (SKEPTIC_ACK.md) and review.
      resume_rule: PHASE_VALIDATION with new evidence.
      resume_phase: PHASE_VALIDATION
  - ENTRYPOINT_GUARD:
      trigger: Entrypoint Guard without acknowledgement.
      owner: Engineering Gatekeeper/OCP.
      required_human_action: conformity confirmation and logging.
      resume_rule: PHASE_PLANNING or PHASE_MICRO_PLANNING depending on scope.
      resume_phase: PHASE_MICRO_PLANNING
  - TAG_APPROVAL_REQUIRED:
      trigger: tag review needed (invalid metadata).
      owner: Domain Gatekeepers (Compliance/Semantic).
      required_human_action: manual approval.
      resume_rule: PHASE_VALIDATION with updated coverage.
      resume_phase: PHASE_VALIDATION
  - INVALID_SEMANTIC_MAPPING:
      trigger: missing or invalid semantic_mapping.yaml.
      owner: Semantic Gatekeeper.
      required_human_action: fix the mapping and log it.
      resume_rule: PHASE_VALIDATION after VALIDATE_MAPPING_SCHEMA.
      resume_phase: PHASE_VALIDATION
  - CONTRACT_ERROR:
      trigger: micro-agent returns CONTRACT_ERROR.
      owner: executing micro-agent notified by Domain Gatekeepers.
      required_human_action: diagnosis and operational action.
      resume_rule: PHASE_EXECUTION or PHASE_VALIDATION depending on the scenario.
      resume_phase: SAME

## Final note
- The timeline remains globally linear; local loops do not break the chain.
- The formal state machine and transitions are documented in a later file, based on this timeline.
