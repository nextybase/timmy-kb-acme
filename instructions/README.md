# instructions/ - Normative Control Plane Specification (Beta 1.0)

## What is this folder?
- **design-first specification repo** for the ProtoTimmy control plane.
- **Single Source of Truth (SSoT)** for Beta 1.0 operational governance.
- **NOT** descriptive documentation or narrative.
- **NOT** an implementation bundle.
- A repository of **verifiable operational contracts**.

Each file here:
- defines **roles, responsibilities, states, gates, transitions, and artifacts**;
- codifies **invariants and explicit failure modes**;
- produces or requires **verifiable artifacts** (Decision Records, states, logs, stop_codes).

Any behavior not described in this folder is **disallowed** in the system.

---

## Definition of Done (Beta 1.0)
- User interaction happens **exclusively through Timmy/ProtoTimmy**.
- Timmy orchestrates Domain Gatekeepers and micro-agents with explicit HiTL coverage.
- OCP (Engineering Gatekeeper) commands Codex and micro-agents through the Control Plane.
- The Prompt Chain is **linear, governed, observable**, with:
  - explicit phase transitions,
  - documented failure modes,
  - noisy stops (no silent degradation).
- The data pipeline is governed end-to-end until the final operational markdown outputs exist.

---

## Non-negotiable rules
- **Every state transition emits an append-only Decision Record** (PASS / BLOCK / FAIL / PASS_WITH_CONDITIONS).
- **State is never inferred** from file combinations or signals; it is asserted only by Decision Records.
- Maintain a sharp separation between:
  - **WHAT** (contracts, invariants, gates, failure modes),
  - **HOW** (implementation, code, tooling).
- No ambiguity about:
  - who decides (Timmy),
  - who validates (Domain Gatekeepers / OCP),
  - who executes (micro-agents).
- **No implicit fallbacks, legacy shims, or silent drops**:
  - every stop, error, or deviation must be explicit,
  - with owner, trigger, and resume rule declared.
- Runtime operates in **strict mode**: if a state cannot be attested, execution halts.

---

## Document inventory (Beta 1.0)
- `00_ssot_agency.md` - **frozen**
- `01_intents_and_actions.md` - **active**
- `02_prompt_chain_lifecycle.md` - **active**
- `03_gatekeepers_contracts.md` - **active**
- `04_microagents_work_orders.md` - **active**
- `05_pipeline_state_machine.md` - **active**
- `06_promptchain_workspace_mapping.md` - **active**
- `07_gate_checklists.md` - **active**
- `08_gate_evidence_and_retry_contract.md` - **active**
- `09_context_layout_contract_beta.md` - **frozen**
- `10_runtime_strict_contract_beta.md` - **active** (runtime invariants and strict-only execution rules)
- `11_ui_contract.md` - **active**
- `12_env_override_capabilities.md` - **active**
- `13_artifacts_policy.md` - **active**
- `14_agent_package_contract.md` - **active**
- `AGENTS.md` - **active**

Active documents may be refined but:
- they must not contradict this README's invariants;
- they must not introduce implicit fallbacks or hidden states.

---

## Official terminology
Canonical epistemic domains:
- **Epistemic Envelope**
- **Agency Engine**

Implementation aliases allowed:
- **Control Plane** → Agency Engine implementation
- **Foundation Pipeline** → Epistemic Envelope implementation

Every document here uses this terminology as its normative reference.

---

## How to work with these documents
- Perform **micro-verbal planning** before editing any file.
- Align every change with the official terminology: Timmy / ProtoTimmy, Domain Gatekeepers, Control Plane, micro-agent.
- Avoid introducing new, unmanaged concepts.
- Prefer:
  - tables,
  - checklists,
  - invariants,
  - failure modes,
  instead of discursive explanations.
- Write in a **normative tone**, using operational and testable statements.

---

## Final warning
This README is the **normative entry point** for Beta 1.0:
- every governance refactor starts here;
- every future implementation must map to these contracts;
- any divergence between code and these specifications is a **bug**, not a choice.

If documentation and code diverge, **documentation wins**.
