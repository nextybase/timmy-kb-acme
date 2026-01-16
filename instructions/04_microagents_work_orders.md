# Micro-agent Work Order Envelope - v1.0

## Scope & Non-goals
- Defines the normative Work Order Envelope contract that micro-agents (Codex included) must obey.
- Non-goal: this document does not describe implementation helpers, repo modules, or UI behavior-those appear elsewhere once the envelope is fulfilled.

## Role Positioning
- Micro-agents execute under Work Order Envelope guidance issued by Domain Gatekeepers/OCP and authorized by Timmy/ProtoTimmy.
- Micro-agents hold zero decision authority: they cannot change the scope, priority, allowed actions, or lifecycle phase encoded in the Work Order.
- Gatekeepers validate; OCP routes; Timmy owns intent decisions; micro-agents act only on validated instructions.

## Work Order Envelope
- Required fields:
  * `intent_id` / `intent_mode`: identifies the registered intent and its phase context (planning, validation, QA, execution).
  * `action_id` / `family`: names the allowed action (`VALIDATE_*`, `GENERATE_*`, `EXECUTE_*`) and confirms it is approved for the current phase.
  * `scope`: documented bounds (inputs, workspaces, constraints) from the Gatekeeper verdict.
  * `expected_outputs`: the allowed StructuredResult values (`OK`, `NEED_INPUT`, `CONTRACT_ERROR`).
  * `inputs`: explicit artifacts (files, prompts, parameter values) the micro-agent must consume.
- Optional fields:
  * `context`: narrative references (related intent, prior prompts) used for traceability.
  * `references`: linked artefacts, logs, or decision memos supporting the request.
  * `notes`: human-readable clarifications; must not alter governance semantics.
- Forbidden fields:
  * Any field that implies scope expansion, action reinterpretation, or policy override.
  * Direct commands to bypass Gatekeeper stops or execute outside the allowed lifecycle phase.

## Allowed Outputs
- `OK`: emitted when the micro-agent completes the requested action against the supplied inputs with no ambiguities.
  * Evidence: structured logs referencing the intent/action (`ai.invocation`, `cli.*`), updated outputs listed in `expected_outputs`, and any generated artefact names.
  * Next owner: Gatekeeper/OCP if further validation is needed; otherwise Timmy updates the intent state.
- `NEED_INPUT`: emitted when required inputs or artefacts are missing or invalid.
  * Allowed when fields in the envelope explicitly list the missing data.
  * Evidence: list of missing artefacts, error logs, expected phase for resubmission.
  * Next owner: Gatekeeper (revalidate inputs) or Timmy (clarify intent if coverage is incomplete).
- `CONTRACT_ERROR`: emitted when the action cannot execute because the envelope was malformed, the action is disallowed in the current phase, or governance signals a HiTL stop.
  * Evidence: stop_code, log event (e.g., `ai.invocation` event `contract_error`), and resume suggestion (referenced stop_condition).
  * Next owner: Gatekeeper (correct scope/coverage) or Timmy (confirm HiTL requirement).

## Stop Conditions & Escalation
1. `malformed_work_order`
   - Trigger: missing required fields or invalid action family.
   - Owner: micro-agent flags `CONTRACT_ERROR` and emits stop_code.
   - Human action: Gatekeeper/Timmy corrects envelope and reissues.
   - Resume: new Work Order validated in same phase.
2. `action_not_allowed`
   - Trigger: requested action family not permitted in current phase (per instructions/02).
   - Owner: micro-agent stops and returns `CONTRACT_ERROR`.
   - Human action: adjust phase coverage or await Gatekeeper confirmation.
   - Resume rule: wait for valid Gatekeeper verdict; phase remains unchanged.
3. `missing_inputs`
   - Trigger: required artefacts listed in `inputs` or evidence of expected outputs absent (`tags_reviewed.yaml`, semantic map).
   - Human action: provide artifacts via Gatekeeper process (tag_onboarding, semantic on-board).
   - Resume phase: typically VALIDATION; resume when inputs present.
4. `hiTL_ambiguity`
   - Trigger: ambiguity flagged by Gatekeeper (stop_code `HITL_REQUIRED`) or OCP.
   - Required action: Timmy confirms, resets `_should_proceed`, documents HiTL memo.
   - Resume: same phase with updated HiTL indicators.

## Traceability & Audit
- Every execution entry must reference the intent/action, lifecycle phase, and Work Order identifier (e.g., `work_order_id`, `phase` metadata in logs).
- Structured logs must include `intent_id`, `action_id`, `phase`, `stop_code`, and StructuredResult to prevent silent success.
- Evidence must be accessible via the artefact list in the Work Order (files touched, outputs generated, log events). No success without traceable outputs.

## Anti-confusion Rules
- Micro-agent ≠ Gatekeeper: micro-agents execute; gatekeepers validate, block, or escalate.
- Micro-agent ≠ Control Plane: the Control Plane routes decisions; the micro-agent obeys the envelope.
- Micro-agent ≠ Timmy: Timmy makes intent decisions, defines allowed Gatekeeper coverage, and authorizes HiTL.
- Execution ≠ Validation ≠ Decision: micro-agent outputs (`OK`, `NEED_INPUT`, `CONTRACT_ERROR`) do not confer decision authority.

## Completion Checklist
- [ ] Work Order Envelope fields populated (intent, action, inputs, expected outputs).
- [ ] StructuredResult logged (OK/NEED_INPUT/CONTRACT_ERROR) with evidence references.
- [ ] stop_code/resume_rule recorded if gatekeepers/OCP requested a halt.
- [ ] Micro-agent never alters prompt scope, allowed actions, or lifecycle phase.
