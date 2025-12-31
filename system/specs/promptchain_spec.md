# Prompt Chain Spec (SSoT)

## 1. Introduction
- **Purpose:** keep the planning phase (Planner → OCP) and the operational work (Codex) strictly separated while ensuring every step remains controlled, traceable, and compliant with the micro-PR discipline.
- **Why a SSoT:** this document is the authoritative reference for actors, expected outputs, governance rules, and template requirements across the Prompt Chain.
- **Principles:** turn-based rigor, micro-PR safety (path safety, atomic I/O), human oversight (HiTL), explicit QA, and strict adherence to the Phase model.
- **Support docs:** `.codex/PROMPTS.md` (template API), `.codex/CHECKLISTS.md` (checklist), `.codex/CLOSURE_AND_SKEPTIC.md` (closure packet), `system/ops/runbook_codex.md` (operational guide).

## 2. Mandatory Turn-Based Protocol
- Planner defines objectives and constraints, never editing the repository.
- OCP translates objectives into numbered prompts, keeps scope narrow, issues one prompt at a time, and never performs edits.
- Codex executes exactly one action per prompt: apply a micro-PR, provide a diff/report, and declare QA outcomes before pausing.
- After Codex responds, OCP evaluates and issues the next prompt (or the closing prompt): no batching, no unsolicited follow-ups, no prompt skipping.
- Every prompt turn must reference this protocol so that all participants remain aligned and the chain remains reproducible.
- **Skeptic Gate (MUST):** after each operational output by Codex (Prompt 1..N and Prompt N+1) the OCP conducts the Skeptic Gate as a decision act; the chain advances only with Decision=PASS, PASS WITH CONDITIONS imposes constraints, BLOCK stops the next phase. The “N+1′” label indicates only the Skeptic Gate after Prompt N+1, not a distinct phase.
- **Evidence Gate:** Prompt 1..N does not advance until the Codex response includes the Active Rules memo, the unified diff, the structured report, and the required QA; the OCP halts the chain without these artifacts.
- **Hard rule OPS/RUN authorization:** no OPS/RUN operational prompt (Phase 1..N or Prompt N+1) may be sent to Codex without an explicit human confirmation recorded by the OCP. The OCP remains the sole owner of the decision to send the prompt, must document it in the report, and activate it before Codex receives instructions. Codex must not request or interpret approvals; it must only respect scope/path-safety and produce the Active Rules memo + diff/report/QA. If the OCP confirmation is missing, the Skeptic Gate blocks progression and the prompt is invalid.

## 3. Verification & Progression Rules
- **Evidence required per step:** each prompt response constitutes progression only when Codex delivers a unified diff, a structured report describing the change and QA results, and, when asked, the intermediate QA output (`pytest -q -k "not slow"` or other tests detailed in the prompt). Those artifacts alone prove that Codex performed the requested work.
- **Delivery policy:** alignment with `main` is not a default step; it happens only when the chain reaches Prompt N+1 (finalization), the OCP explicitly authorizes it, or a runtime change cannot remain confined to diff/report/QA. Synchronization is an explicit event, never implicit.
- **OCP decision gate:** only the OCP decides whether the evidence is sufficient to advance the chain or request further iterations; Codex waits for the next OCP prompt before moving forward, reporting the artifacts produced and any blockers.
- **Prompt formatting requirement:** OCP → Codex prompts must be delivered as a single copyable structured block (see `.codex/PROMPTS.md`) to prevent ambiguity and ensure reproducibility.
- **Encoding guard (docs/README):** documentation under `docs/` and `README.md` are protected by a mojibake guard using `tools/fix_mojibake.py` and `tests/encoding/test_docs_encoding.py`; the guard is a governance check on documentation quality and does not introduce runtime behavior.

## 4. Prompt Chain Phase Model
The Prompt Chain unfolds in three clearly delimited phases that map to numbered prompts. Each phase carries a precise mandate, acceptable actions, and deliverables.

### 4.1 Phase 0 – Analytical, read-only prompts (Prompt 0, 0x)

**Normative clarification (v1.1):** Prompt 0x (0a, 0b, … 0n) are not legacy, fallback, or deprecated. They are a formal extension of Phase 0 and an integral part of controlled uncertainty reduction.

#### Phase 0 — Purpose
Phase 0 exists to:
- build a shared, verifiable understanding of the system;
- identify constraints, risks, and objectives;
- make explicit the remaining uncertainties that prevent safe action.

Phase 0 does not aim at exhaustiveness; it aims at mapping the relevant ignorance.

#### Prompt 0 — Official entrypoint (role and limits)
Prompt 0 is the official entrypoint into the Prompt Chain. It is valid even when the output is:
- incomplete information;
- a list of open questions;
- an explicit inability to formulate a robust operational plan.

A Prompt 0 that declares missing information is a correct outcome, not a failure.

#### Prompt 0x — Exploratory Prompts
Prompt 0x prompts are Phase 0 read-only deep-dives, used exclusively during Phase 0.
Their purpose is to close specific uncertainties that emerged from:
- Prompt 0;
- previous Prompt 0x prompts.

**Epistemic governance (core rule):** Prompt 0x is not a procedural fallback. It persists until the OCP deems the information state sufficient to authorize entry into the operational phase.

#### Admissibility rules (Prompt 0x)
A Prompt 0x is admissible only if it:
- addresses an uncertainty explicitly declared in a previous prompt;
- has a distinct, non-redundant informational scope;
- is entirely read-only (no edits, no patch/diff, no build, no tests, no execution);
- is explicitly authorized by the OCP.

#### Allowed actions in Phase 0 (read-only inspections)
Phase 0 forbids any write, patch/diff generation, formatting, QA commands, tests, or builds.
Read-only inspection commands are permitted only if explicitly whitelisted by the OCP in the prompt itself (Prompt 0 or Prompt 0x), to keep SSoT ingestion verifiable.

#### Exit condition (leaving Phase 0)
Leaving Phase 0 is not automatic nor numerical. Phase 0 ends only when the OCP records the formal human decision that the achieved information level is sufficient to formulate a robust, safe, and effective operational plan.
This declaration is a governance act and a prerequisite to issuing any operational prompt (Prompt 1..N).

#### Non-return rule (important)
Once the operational phase starts (Prompt 1), the emergence of new structural uncertainties must not be resolved via new Prompt 0x prompts; it is a BLOCK condition for the Prompt Chain.

### 4.2 Phase 1..N – Operational micro-PR prompts
- Purpose: implement scoped changes defined by the OCP while honoring path safety, template structure, and the Active Rules memo.
- Each prompt must emit a unified diff, a structured report, a DoD section, and at least `pytest -q -k "not slow"` (or a justified alternative) before moving forward.
- Codex must apply changes only to the files declared in the prompt, document assumptions, and run targeted tests when requested.
- Changes under `tests/**` are permitted only as a consequence of scoped changes outside `tests/**`, and any test touch must include a Test Impact Map in the report.
- If the DoD is not met, follow-on prompts must be numbered as sub-iterations (e.g., 1a/1b/1c or Na/Nb/Nc) until the DoD is satisfied.
- **Skeptic Gate template (MUST):** Evidence check (memo/diff/report/QA presenti?) [YES/NO]; Scope check (file autorizzati?) [YES/NO]; Risk check (nuovi rischi/edge cases?) [OK/NOTED/BLOCK]; Decision: PASS / PASS WITH CONDITIONS / BLOCK.
- After each operational Codex response, the **Skeptic Gate** is activated by the OCP: the gate is a governance act, not an operational task of Codex. The OCP evaluates risks and limits, records observations, and decides whether to issue the next prompt; Codex may flag problems but cannot authorize phase progression.

### 4.3 Prompt N+1 - Final QA and chain closure
- Purpose: verify the entire change set with the full QA stack (`pre-commit run --all-files`, `pytest -q`), summarize the chain, emit a one-line closing commit message in Italian (unless explicitly instructed otherwise), and record the Retrospective.
- Codex may apply up to ten micro-fixes to satisfy QA; each rerun is documented in the report.
- Only after both QA commands pass, the closing summary is issued, and the Retrospective is logged as PASS (notes/TODO facoltativi) may the chain be considered complete.

## 5. Mandatory Language Policy
- All canonical documentation, templates, and artifacts referenced by the Prompt Chain are maintained in English, preserving the SSoT character.
- Default conversational rule: Codex replies in Italian for the chain, except when the OCP explicitly enters control mode (OCP ↔ Codex exchanges) which are English-only; Timmy/ProtoTimmy ↔ User stays Italian-only. Treat this as the sole approved override to the Italian default.
- When not under the OCP control exception, conversations between Planner, OCP, and Codex must remain Italian to keep the human-in-the-loop flow consistent with this policy.

## 6. Prompt Template Expectations
- Templates for Prompt 0, Prompt 0x, Prompt 1..N, and Prompt N+1 live in `.codex/PROMPTS.md` and define the mandatory sections that each prompt must declare (purpose, allowed files, Active Rules memo, phase constraints, tests, etc.).
- Operational prompts (Phase 1..N) are the only ones authorized to generate diffs, touch files, and execute the intermediate QA mentioned above; Phase 0 prompts remain analytical, and Prompt N+1 focuses on final QA plus narrative closure.
- Every prompt must embed the Active Rules memo at the start of the response to remind all stakeholders of path safety, micro-PR scope, QA requirements, and the language policy.
- SPIKE prompts are permitted as read-only analytical follow-ups (no edits, no QA) and must use the naming convention `SPIKE PRE PROMPT N` / `SPIKE POST PROMPT N` with optional variants (`SPIKE A/B/...`); see `.codex/PROMPTS.md` for the short template.

  ### 6.1 Canonical Prompt Header
  - The canonical template requires that every prompt begins with the block:

```
ROLE: Codex
PHASE: ...
SCOPE: ...
ACTIVE RULES MEMO: ...
EXPECTED OUTPUTS: ...
TESTS: ...
CONSTRAINTS: ...
STOP RULE: ...
```

    The `ROLE: Codex` line must precede any operational detail: without it the OCP considers the prompt incomplete and the Skeptic Gate will not authorize progression. The template blocks advancement when `ROLE` is missing or replaced, preventing prompts copied from OCP or other sources from improperly assuming Codex’s role. Evidence Gate and Skeptic Gate verify that the block is present before assessing content, limits, and risks.

  ## 7. Protocol Violations (do not do)
- Breaking the Planner→OCP→Codex→OCP→Planner turn order or issuing multiple actions per prompt.
- Executing edits/QA during Phase 0 or skipping Phase N+1 altogether.
- Responding in any language other than Italian when not explicitly allowed.
- Touching files that lie outside the scope declared by the active prompt or the SSoT.
- Omitting the Active Rules memo or failing to document QA attempts and retries.
- Adding unsolicited end-of-task questions or prompts for extra checks not requested by the OCP.

## 8. Part A – Governance (Planner + OCP)

### 8.1 Actors
- **Human/Planner:** defines the business goals, constraints, and success criteria and authorizes OPS/RUN prompts; it does not modify the repository or run commands.
- **OCP (OrchestratoreChainPrompt):** translates Planner directives into numbered prompts, enforces this spec (sections 2-6), applies governance gates within the human-authorized envelope, and never edits files.
- **Codex:** executes the current prompt alone, without decision agency, respecting the declared scope, template, Active Rules memo, and the Phase model before pausing for the next instruction.

### 8.2 Onboarding Task Codex (mandatory entry point)
- Runs once at the start of every chain, ensuring Codex loads `.github/codex-instructions.md`, `system/ops/agents_index.md`, the relevant `AGENTS.md`, `.codex/AGENTS.md`, and the other SSoT documents listed in `.codex/PROMPTS.md`.
- Establishes path safety, QA expectations, and the requirement to plan before coding; sets the tone for micro-PR discipline.
- Activates the Phase model: Prompt 0 (analysis) always precedes any operational prompt; skipping or collapsing phases is forbidden.

### 8.3 Prompt Chain definition
- The chain is a numbered, turn-based sequence (Prompt 0…N+1) with a clear scope for each prompt as per section 6.
- Each prompt addresses a single concern; no prompt may inject future requests, combine unrelated scopes, or expand its declared file set.
- Prompt templates require the Active Rules memo, list of allowed/prohibited files, expected outputs (diff/report/QA), and explicit statements about the phase and language policy.

### 8.4 Prompt Chain lifecycle
- **Kick-off:** Human/Planner decides on the chain; Onboarding Task codifies the plan and loads the SSoT; only after this may the OCP issue Prompt 0.
- **Execution:** OCP issues prompts sequentially; Codex responds with one micro-PR (diff + report + intermediate QA), then waits for the next prompt. Each operational response includes the memo from section 6 and confirms compliance with the turn-based protocol.
- **Closure:** OCP issues Prompt N+1 with final QA requirements; Codex runs `pytest -q` and `pre-commit run --all-files` (repeating up to ten times if needed), documents every rerun, summarizes the entire chain, records the Retrospective PASS (optional notes/TODO), and ends with a one-line Italian commit message. The post-N+1 Skeptic Gate (sometimes labeled “N+1′”) remains a governance gate, not a phase.
- If QA fails more than twice per prompt, Codex rewrites the patch and retries; after the third failure, Codex explicitly requests guidance from the OCP.

## 9. Part B – Operational Contract for Codex

### 9.1 What is a Prompt Chain for Codex?
- A sequence of numbered prompts aligned to the Phase model; Codex must execute only the current prompt and never anticipate future phases.
- Each prompt corresponds to a micro-PR defined in the template from section 6 and obeys the mandatory language policy from section 5.

### 9.2 Core rules
- Respect path safety, atomic writes, the AGENTS matrices, this spec, and the QA pipeline (intermediate `pytest -q -k "not slow"`, final `pytest -q` + `pre-commit run --all-files`).
- Run the static pre-check described in `.codex/PROMPTS.md` before generating a patch; failing pre-checks halt QA and require corrective action.
- Handle retries cleanly, document them in each report, and stop to ask the OCP if the same issue persists after two autocorrections.
- Conversational exchanges stay Italian unless the OCP invokes the control-mode exception (OCP ↔ Codex English-only); Timmy/ProtoTimmy ↔ User remains Italian-only.
- **Trial window:** the Skeptic Gate is MUST for the next two complete Prompt Chains; after the second cycle the OCP leads a mandatory retrospective to decide whether to keep it or retune it.

### 9.3 Prompt format
- Every prompt declares purpose, allowed/prohibited files, expected outputs (diff, report, QA), and explicit prohibitions as defined in `.codex/PROMPTS.md`.
- The Active Rules memo from section 6 must appear at the start of every operational response.

### 9.4 Required output per prompt
- Provide a unified diff when changes exist.
- Deliver a structured report describing the changes, their impact, the QA executed, and suggested next steps.
- Mention any assumptions, blockers, or unanswered questions.

### 9.5 Anti-patterns
- Combining unrelated domains in the same prompt, touching unspecified files, adding spurious context outside the template, or neglecting the memo/language/phase guardrails.

## 10. Codex Smoke Chain – Diagnostic Test
- Objective: simulate a miniature Prompt Chain (S0–S4) to prove turn-taking, memo awareness, QA policy, escalation limits, Italian language, and pre-check validation without editing the repo.
- Flow:
  - S0: OCP sends a toy prompt; Codex acknowledges the Active Rules memo.
  - S1: Codex describes how it would pre-check a mock diff with no files changed.
  - S2: OCP issues a sample operational prompt; Codex replies conceptually with a micro-PR summary.
  - S3: Codex states the intermediate QA (`pytest -q -k "not slow"`) it would run, explaining how it would interpret the outcome without executing the command.
  - S4: Codex describes the escalation path (max two autocorrections), the final QA (`pytest -q` + `pre-commit run --all-files`), and reconfirms Italian-language compliance.
- Rules: no disk writes, no QA execution, always respect path safety, micro-PR discipline, and the Italian-only policy.
- Use cases: governance health check, Prompt Chain metadata validation, and documentation of OCP→Codex alignment.
