# UI Contract — v1.0

## Scope & Non-goals
- Defines WHAT UI surfaces may present, trigger, and document when interacting with the Prompt Chain.
- Non-goal: UI frameworks, component layouts, or implementation techniques.

## UI Role in the Agency Model
- UI surfaces are execution surfaces that relay intents/actions from humans to micro-agents; they do not decide which intents to register, which Gatekeepers to invoke, or how governance applies.
- UI displays pipeline state, lifecycle phase, and stop_codes without altering them; Timmy and Gatekeepers control the contract.

## State & Phase Gating
- Each UI affordance must map to a single pipeline state (`WORKSPACE_BOOTSTRAP`, `SEMANTIC_INGEST`, `FRONTMATTER_ENRICH`, `VISUALIZATION_REFRESH`, `PUBLISH_PREP`) and lifecycle phase (PLANNING, VALIDATION, EXECUTION, QA, etc.).
- Affordances tied to a state may be disabled when the required artefacts or validated inputs are missing.
- UI must not surface actions outside the allowed family for the current phase (`VALIDATE_*` → VALIDATION/QA, `EXECUTE_*` only after validation, etc.).

## Action Triggering Rules
- UI only triggers registered actions listed in the Intent’s `allowed_actions`; triggers come with the Work Order Envelope metadata (intent_id, action_id, phase, pipeline state).
- Each trigger records the selected Intent, Action family, phase, and state in structured logs (`ui.action.start`, `ai.invocation`) for traceability.
- UI must refuse to call actions marked `CONTRACT_ERROR` or not in the current state’s allowed families.

## HiTL & Stop Handling
- When a stop_code (`HITL_REQUIRED`, `ContractError`, etc.) is active, UI displays the verbatim stop condition and required human action from the Gatekeeper/OCP.
- UI may collect human input only if the stop explicitly requests it (`_should_proceed`, form input for missing artifacts) and logs the input before routing it.
- UI must never auto-resume; resume occurs only when the owned resume_rule/resume_phase in the stop condition is satisfied and recorded.

## Failure Modes
- Invalid state/action: UI must block the action, log `ui.action.blocked`, and inform the user that governance disallows the request.
- Missing prerequisites: UI surfaces note the missing artefacts (e.g., tags, semantic map) and refer to the responsible Gatekeeper.
- Active stop_code: UI shows the stop with owner attribution; no implicit action allowed.
- Artefact inconsistencies (e.g., pipeline state claims `FRONTMATTER_ENRICH` but `book/*.md` missing) require a stop_code `ContractError` and Gatekeeper investigation, not automatic skip.

## Anti-confusion Rules
- UI ≠ Timmy: UI presents options; Timmy decides intents and HiTL.
- UI ≠ Gatekeeper: UI renders verdicts but cannot override them.
- UI ≠ Control Plane: UI triggers actions; the Control Plane applies gate logic and enforces stop/resume.
- UX conveniences (shortcuts, previews) never equate to governance exceptions; every decision must align with the established contract.

## Completion Checklist
- [ ] Each UI action maps to a Work Order Envelope with intent_id, action_id, phase, state.
- [ ] Active stop_codes are shown verbatim with owner/required action.
- [ ] Disabled affordances remain disabled until Gatekeeper/OCP clears the stop.
- [ ] Logs capture StructuredResult and reference artifacts for every triggered action.
