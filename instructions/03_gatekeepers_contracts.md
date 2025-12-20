# Gatekeepers Contracts — v1.0

## Scope & Non-goals
- Defines the contractual obligations for Domain Gatekeepers and the Engineering Gatekeeper (OCP role) within the Prompt Chain.
- Non-goal: this file does not describe pipeline modules or UI flows; implementation lives elsewhere.

## Role Mapping
- **ProtoTimmy / Timmy**: orchestrates intent registration, selects covered Gatekeepers, records decisions, and triggers HiTL.
- **Domain Gatekeepers**: validate artifacts, guard policy, issue blocks, escalate to Timmy, and coordinate micro-agents under Work Order Envelope.
- **Engineering Gatekeeper (OCP)**: applies the Control Plane (not itself an agent) to enforce HiTL stops, route prompts to micro-agents, and log verdicts.
- **Micro-agents**: execute REGISTER_/VALIDATE_/GENERATE_/EXECUTE_ actions; return StructuredResult (`OK`, `NEED_INPUT`, `CONTRACT_ERROR`) and do not make governance decisions.

## Contract Invariants
- Gatekeepers defend WHAT: every intent must list mandatory/advisory Gatekeepers; approvals exist only when these Gatekeepers' verdicts allow progress.
- Blocks surface via stop_codes (`HITL_REQUIRED`, `ContractError`, `TagsInvalid`, `MappingInvalid`) and cannot be overridden without explicit HiTL from Timmy.
- Gatekeeper verdicts depend on artifacts defined by the intent (semantic mapping, tags, config); engineering Gatekeeper records timestamps/logs before dispatching micro-agents.
- Micro-agents may only execute actions after Gatekeepers sign off for the current phase; any deviation emits `CONTRACT_ERROR`.
- OCP enforces sequential prompt flow: Gatekeeper verdict → HiTL evaluation → micro-agent Work Order Envelope dispatch.

## Evidence & Artefacts
- **Inputs**: intent spec (mandatory/advisory coverage), semantic_mapping.yaml, tags_reviewed.yaml, config/config.yaml, stop_code history, structured logs (`ai.invocation`, `cli.*` events).
- **Outputs**: gatekeeper audit log entry (structured event e.g., `ai.invocation` fields `event=gatekeeper.verdict`), stop_code file, prompt memo to Timmy, attachments (e.g., `tags_reviewed.yaml`, `_should_proceed` flag), and updated HiTL indicators (`_CODEX_HITL_KEY`, `_should_proceed`).
- **Artifacts produced**: `tags_reviewed.yaml` (approval checkpoint), `semantic/kg.tags.*` or `semantic/tags.db` snapshots, documentation when a gate causes a restart, and explicit HiTL records in OCP logs.

## Validation Families & Phase Alignment
- `VALIDATE_*`: executed only during VALIDATION or QA phases (per instructions/02). These actions verify schema, tags, mapping, and governance invariants.
- `GENERATE_*`: allowed only after Gatekeeper validation; generate new documentation/artifacts with explicit logging.
- `EXECUTE_*`: trigger side effects (push, pipeline run) and must follow `VALIDATE_*` success and any required HiTL acknowledgments.

## Stop Conditions & HiTL
```yaml
stop_conditions:
  - name: HITL_REQUIRED
    trigger: gatekeeper detects policy/semantic failure or missing coverage
    owner: OCP (Engineering Gatekeeper) logs and issues stop_code
    required_human_action: Timmy/OCP review and confirm `_should_proceed` flag
    resume_rule: gatekeeper verdict updated + HiTL cleared
    resume_phase: SAME
  - name: ContractError
    trigger: micro-agent returns CONTRACT_ERROR under Work Order Envelope
    owner: Domain Gatekeeper → Timmy
    required_human_action: intent review, file corrections, repeat validation
    resume_rule: artifacts corrected, validation rerun
    resume_phase: SAME
  - name: TAG_APPROVAL_REQUIRED
    trigger: missing `tags_reviewed.yaml` or invalid tags
    owner: Domain Gatekeeper
    required_human_action: regenerate tags via tag_onboarding + re-validate
    resume_rule: new `tags_reviewed.yaml` created, intent coverage reaffirmed
    resume_phase: VALIDATION
  - name: SKEPTIC_GATE
    trigger: policies (e.g., `system/specs/promptchain_spec.md`) raise higher-level conflict
    owner: OCP as Control Plane
    required_human_action: escalate to Timmy + document justification in memo
    resume_rule: Timmy approves or reroutes intent
    resume_phase: SAME or PREVIOUS depending on instruction clause
```

## Anti-confusion Rules
- **Gate ≠ Agent**: Gatekeepers validate and block; they do not execute code. Agents (Codex/micro-agents) run under Work Order Envelope and obey gate verdicts.
- **Control Plane ≠ Engineering Gatekeeper**: The Control Plane is the orchestration layer; the Engineering Gatekeeper is its agent role that carries verdicts, not the entire plane.
- **Timmy is the sole global decision authority**; gatekeepers and micro-agents must escalate and document rather than override.

## Completion Checklist
- [ ] Mandatory/advisory Gatekeepers listed in intent coverage.
- [ ] Required artifacts (`tags_reviewed.yaml`, semantic mapping, logs) present before moving to next phase.
- [ ] StructuredResult logged (`ai.invocation`/`cli.*`) with event names matching the verdict.
- [ ] Stop codes recorded in artefact store when a gate blocks execution.
- [ ] HiTL triggers documented (`_CODEX_HITL_KEY`, `_should_proceed` resets).
