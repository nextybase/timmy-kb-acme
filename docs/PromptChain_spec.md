# Prompt Chain Spec (SSoT)

## 1. Introduction
- **Purpose:** keep the planning phase (Planner → OCP) and the operational work (Codex) strictly separated while ensuring every step remains controlled, traceable, and compliant with the micro-PR discipline.
- **Why a SSoT:** this document is the authoritative reference for actors, expected outputs, governance rules, and template requirements across the Prompt Chain.
- **Principles:** turn-based rigor, micro-PR safety (path safety, atomic I/O), human oversight (HiTL), explicit QA, and strict adherence to the Phase model.

## 2. Mandatory Turn-Based Protocol
- Planner defines objectives and constraints, never editing the repository.
- OCP translates objectives into numbered prompts, keeps scope narrow, issues one prompt at a time, and never performs edits.
- Codex executes exactly one action per prompt: apply a micro-PR, provide a diff/report, and declare QA outcomes before pausing.
- After Codex responds, OCP evaluates and issues the next prompt (or the closing prompt): no batching, no unsolicited follow-ups, no prompt skipping.
- Every prompt turn must reference this protocol so that all participants remain aligned and the chain remains reproducible.

## 3. Verification & Progression Rules
- **Evidence required per step:** each prompt response constitutes progression only when Codex delivers a unified diff, a structured report describing the change and QA results, and, when asked, the intermediate QA output (`pytest -q -k "not slow"` or other tests detailed in the prompt). Those artifacts alone prove that Codex performed the requested work.
- **Push policy:** pushing to `main` is _not_ a default step; it happens only when the chain reaches Prompt N+1 (finalization), the OCP explicitly authorizes a push, or a change affects runtime behavior that cannot stay confined to a reviewable diff/report/QA set. The push is a synchronization event, never an implicit requirement.
- **OCP decision gate:** only the OCP decides whether the evidence is sufficient to advance the chain or request further iterations; Codex waits for the next OCP prompt before moving forward, reporting the artifacts produced and any blockers.
- **Prompt formatting requirement:** OCP → Codex prompts must be delivered as a single copyable structured block (see `.codex/PROMPTS.md`) to prevent ambiguity and ensure reproducibility.

## 4. Prompt Chain Phase Model
The Prompt Chain unfolds in three clearly delimited phases that map to numbered prompts. Each phase carries a precise mandate, acceptable actions, and deliverables.

### 4.1 Phase 0 – Analytical, read-only prompts (Prompt 0, 0a..0x)
- Objective: load every SSoT document, surface ambiguities, and design the operational plan without touching the filesystem.
- Codex responses must focus on structured reasoning (plans, mappings, risks) and cite the documents reviewed.
- No patch, diff, or QA command may be executed in this phase.

### 4.2 Phase 1..N – Operational micro-PR prompts
- Purpose: implement scoped changes defined by the OCP while honoring path safety, template structure, and the Active Rules memo.
- Each prompt must emit a unified diff, a structured report, and at least `pytest -q -k "not slow"` (or a justified alternative) before moving forward.
- Codex must apply changes only to the files declared in the prompt, document assumptions, and run targeted tests when requested.

### 4.3 Prompt N+1 – Final QA and chain closure
- Purpose: verify the entire change set with the full QA stack (`pre-commit run --all-files`, `pytest -q`), summarize the chain, and emit a one-line closing commit message in Italian (unless explicitly instructed otherwise).
- Codex may apply up to ten micro-fixes to satisfy QA; each rerun is documented in the report.
- Only after both QA commands pass and the closing summary is issued may the chain be considered complete.

## 5. Mandatory Language Policy
- All canonical documentation, templates, and artifacts referenced by the Prompt Chain are maintained in English, preserving the SSoT character.
- Codex must respond exclusively in Italian in every prompt of the chain, including embedded reports and QA summaries, unless a prompt explicitly authorizes another language.
- Conversations between Planner, OCP, and Codex must remain Italian to keep the human-in-the-loop flow consistent with this policy.

## 6. Prompt Template Expectations
- Templates for Prompt 0, Prompt 0a..0x, Prompt 1..N, and Prompt N+1 live in `.codex/PROMPTS.md` and define the mandatory sections that each prompt must declare (purpose, allowed files, Active Rules memo, phase constraints, tests, etc.).
- Operational prompts (Phase 1..N) are the only ones authorized to generate diffs, touch files, and execute the intermediate QA mentioned above; Phase 0 prompts remain analytical, and Prompt N+1 focuses on final QA plus narrative closure.
- Every prompt must embed the Active Rules memo at the start of the response to remind all stakeholders of path safety, micro-PR scope, QA requirements, and the language policy.

## 7. Protocol Violations (do not do)
- Breaking the Planner→OCP→Codex→OCP→Planner turn order or issuing multiple actions per prompt.
- Executing edits/QA during Phase 0 or skipping Phase N+1 altogether.
- Responding in any language other than Italian when not explicitly allowed.
- Touching files that lie outside the scope declared by the active prompt or the SSoT.
- Omitting the Active Rules memo or failing to document QA attempts and retries.

## 8. Part A – Governance (Planner + OCP)

### 8.1 Actors
- **Planner:** defines the business goals, constraints, and success criteria; it does not modify the repository or run commands.
- **OCP (OrchestratoreChainPrompt):** translates Planner directives into numbered prompts, enforces this spec (sections 2-6), ensures each prompt covers one turn, and never edits files.
- **Codex:** executes the current prompt alone, respecting the declared scope, template, Active Rules memo, and the Phase model before pausing for the next instruction.

### 8.2 Onboarding Task Codex (mandatory entry point)
- Runs once at the start of every chain, ensuring Codex loads `docs/AGENTS_INDEX.md`, the relevant `AGENTS.md`, `.codex/AGENTS.md`, and the other SSoT documents listed in `.codex/PROMPTS.md`.
- Establishes path safety, QA expectations, and the requirement to plan before coding; sets the tone for micro-PR discipline.
- Activates the Phase model: Prompt 0 (analysis) always precedes any operational prompt; skipping or collapsing phases is forbidden.

### 8.3 Prompt Chain definition
- The chain is a numbered, turn-based sequence (Prompt 0…N+1) with a clear scope for each prompt as per section 6.
- Each prompt addresses a single concern; no prompt may inject future requests, combine unrelated scopes, or expand its declared file set.
- Prompt templates require the Active Rules memo, list of allowed/prohibited files, expected outputs (diff/report/QA), and explicit statements about the phase and language policy.

### 8.4 Prompt Chain lifecycle
- **Kick-off:** Planner decides on the chain; Onboarding Task codifies the plan and loads the SSoT; only after this may the OCP issue Prompt 0.
- **Execution:** OCP issues prompts sequentially; Codex responds with one micro-PR (diff + report + intermediate QA), then waits for the next prompt. Each operational response includes the memo from section 6 and confirms compliance with the turn-based protocol.
- **Closure:** OCP issues Prompt N+1 with final QA requirements; Codex runs `pytest -q` and `pre-commit run --all-files` (repeating up to ten times if needed), documents every rerun, summarizes the entire chain, and ends with a one-line Italian commit message.
- If QA fails more than twice per prompt, Codex rewrites the patch and retries; after the third failure, Codex explicitly requests guidance from the OCP.

## 9. Part B – Operational Contract for Codex

### 9.1 What is a Prompt Chain for Codex?
- A sequence of numbered prompts aligned to the Phase model; Codex must execute only the current prompt and never anticipate future phases.
- Each prompt corresponds to a micro-PR defined in the template from section 6 and obeys the mandatory language policy from section 5.

### 9.2 Core rules
- Respect path safety, atomic writes, the AGENTS matrices, this spec, and the QA pipeline (intermediate `pytest -q -k "not slow"`, final `pytest -q` + `pre-commit run --all-files`).
- Run the static pre-check described in `.codex/PROMPTS.md` before generating a patch; failing pre-checks halt QA and require corrective action.
- Handle retries cleanly, document them in each report, and stop to ask the OCP if the same issue persists after two autocorrections.
- All conversational exchanges with OCP and Planner must stay Italian.

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
