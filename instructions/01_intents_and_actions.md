Agency & Orchestration Model - v1.0 - Intents & Actions

## Essential Definitions
- **User Intent**: narrative snippet from the user describing a requirement to fulfill; it triggers a request to ProtoTimmy.
- **System Intent**: the technical counterpart of a User Intent, documented in the registry; it becomes operational only when ProtoTimmy explicitly registers it through the `REGISTER_INTENT` Action.
- **Actions & Modes**: every Intent or Action references an external taxonomy of operating modes (`analysis`, `report`, `spike`, `ops-run`, `coding`, etc.); that taxonomy is assumed and not redefined here.
- **Registry**: the set of documented Intent and Action definitions under `instructions/`; the registry is dynamic only insofar as ProtoTimmy may add new System Intents and Actions through the appropriate actions, always under HiTL governance.

## Managed Registry Dynamics
- **ProtoTimmy** is the only entity authorized to register new System Intents or Actions during planning or micro-planning, as defined in the Prompt Chain lifecycle; Domain Gatekeepers only receive what is already documented.
- **Intent Registration**: possible only through the `REGISTER_INTENT` Action (template below).
- **Action Registration**: possible only through the `REGISTER_ACTION` Action (template below).
- **Whitelist Actions**: Gatekeepers and micro-agents execute only Actions listed in the registry; any undocumented Action is ignored or leads to `CONTRACT_ERROR`.
- **Micro-agent executes, does not decide**: executing agents (e.g., Codex) do not assess whether an Action should exist; they just execute what is registered and return OK / NEED_INPUT / CONTRACT_ERROR.
- **HiTL for registrations**: every `REGISTER_INTENT` or `REGISTER_ACTION` mandates explicit HiTL; modifying a Gatekeeper's coverage over an Intent also requires HiTL; the same applies to `stop_code == "HITL_REQUIRED"`.

## Registry invariants (non-negotiable constraints)
- Only ProtoTimmy may perform `REGISTER_INTENT` / `REGISTER_ACTION` during PLANNING or MICRO_PLANNING; Domain Gatekeepers and micro-agents can only consume what is already registered.
- Any Action not present in the registry triggers `CONTRACT_ERROR` or is ignored by Gatekeepers/micro-agents and halts the chain.
- The `allowed_actions` field acts as a whitelist per Intent: without an explicit presence the Action is illegitimate in the context.
- The family (`VALIDATE_*` vs `GENERATE_*` / `EXECUTE_*`) must align with the current phase (see `02_prompt_chain_lifecycle.md`); otherwise the chain requires correction via micro-planning.

## Coverage Domain Gatekeepers
- Every documented System Intent declares which Domain Gatekeepers are **mandatory** and which are **advisory** for the request.
- ProtoTimmy invokes exactly those Gatekeepers, without ad-hoc variations; advisory Gatekeepers may report blocks or recommendations, while a mandatory Gatekeeper can halt the chain and ProtoTimmy orchestrates globally respecting explicit HiTL triggers; that block is a domain verdict that Timmy cannot bypass without HiTL/governance.
- Coverage is an attribute of the Intent registry and may be updated only through HiTL and `REGISTER_INTENT`.

## Action taxonomy
- Actions belong to the following families:
  1. `VALIDATE_*` - checks with no side effects (schema, state, gate).
  2. `GENERATE_*` - document/artifact generation (README, reports).
  3. `EXECUTE_*` - workspace/pipeline side effects (push, CLI pipelines).
- An Action may be invoked only if it is registered and the family matches the expected behavior.

## HiTL triggers
- Mandatory needs:
  - `REGISTER_INTENT` → HiTL.
  - `REGISTER_ACTION` → HiTL.
  - Modifying the Gatekeeper coverage for an Intent → HiTL.
  - Receiving `stop_code == "HITL_REQUIRED"` → HiTL, with execution blocked until supervision.
- Domain Gatekeepers report HiTL triggers through `message_for_ocp` (legacy field intended as *message_for_gatekeeper*, not a direct channel to a specific agent) and reset `_CODEX_HITL_KEY` only after confirmation.

## Minimal failure modes (and required handling)
- Requesting an unregistered Action → `CONTRACT_ERROR` + immediate stop (no execution) and log entry; the actor reports NEED_INPUT.
- Registered Action but outside `allowed_actions` → `CONTRACT_ERROR` + stop and notification to ProtoTimmy for realignment.
- Phase/family mismatch (e.g., `GENERATE_*` during `VALIDATION`) → stop and correction request via micro-planning (`resume_phase: SAME`).
- Conflict between an advisory recommendation and a blocking mandatory Gatekeeper → stop + HiTL escalation toward ProtoTimmy (scheduled `need_input`).
- `stop_code == "HITL_REQUIRED"` or tag approval gate → stop + human confirmation required before proceeding.

## Operational templates

### INTENT SPEC (System Intent)

```yaml
intent_id: ""
name: ""
description: ""
intent_mode: "" # (analysis/report/spike/ops-run/coding/etc.)
preconditions:
  - ""
postconditions:
  - ""
inputs:
  - name: ""
    type: ""
outputs:
  - name: ""
    type: ""
coverage:
  mandatory_gatekeepers:
    - ""
  advisory_gatekeepers:
    - ""
allowed_actions:
  - ""
hitl_triggers:
  - REGISTER_INTENT
  - REGISTER_ACTION
  - MODIFY_COVERAGE
  - stop_code == "HITL_REQUIRED"
evidence_required:
  - log: ""
  - artifact: ""
```
Rule: within the context of this Intent, only the Actions listed in `allowed_actions` may be invoked.
Constraint: `allowed_actions` is required and cannot be empty for valid Intents.

### ACTION SPEC

```yaml
action_id: ""
name: ""
family: VALIDATE_|GENERATE_|EXECUTE_
action_mode: ""
side_effects: "" # dichiarati e tracciati
executor: "" # es. Codex
steps:
  - description: ""
    command: ""
    # per family EXECUTE_* gli side_effects devono essere espliciti.
rollback_restart_notes:
  - ""
outputs:
  - OK
  - NEED_INPUT
  - CONTRACT_ERROR
stop_conditions:
  - ""
```

## Complete example
- **User Intent → System Intent:** the user requests "update the semantic mapping".
- **Coverage Gatekeepers:**
  - mandatory: Semantic Gatekeeper.
  - advisory: Compliance Gatekeeper.
- **Action sequence**
  1. `VALIDATE_MAPPING_SCHEMA` (`VALIDATE_*`).
  2. `GENERATE_MAPPING_ARTIFACTS` (`GENERATE_*`).
  3. `EXECUTE_DEPLOY_MAPPING` (`EXECUTE_*`).
- Each Action executes only after it is present in the registry and aligns with the correct family; every step refers to the templates above and returns OK/NEED_INPUT/CONTRACT_ERROR. The sequence is allowed only if compatible with the current Prompt Chain phase.

## Disclaimer
- `message_for_ocp` is a legacy field name; conceptually it is a *message_for_gatekeeper* addressed to a Domain Gatekeeper, not to a single agent, and it does not imply automatic execution. It neither authorizes nor implies direct invocation of a specific agent: routing is decided by ProtoTimmy based on the Intent coverage.
