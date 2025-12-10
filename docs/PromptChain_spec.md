# Prompt Chain Spec (SSoT)

## 1. Introduction
- **Purpose:** separate the planning phase (Planner -> OCP) from the operational work (Codex), ensuring that every step remains controlled, traceable, and compliant with micro-PR discipline.
- **Why a SSoT:** avoid fragmentation across docs, provide a single reference for actors, rules, and expected outputs.
- **Principles:** micro-PRs, safety (path safety, atomic I/O), human oversight (HiTL), and explicit QA.

## 2. Part A - Governance (Planner + OCP)

### 2.1 Actors
- **Planner:** defines objectives, decides whether to proceed, adjust, or close the chain; it never touches the code.
- **OCP (OrchestratoreChainPrompt):** translates planner objectives into numbered prompts (Prompt 0, 1, ...), maintains scope and order, and never edits the repo.
- **Codex:** executes one prompt at a time as the repo-aware agent; applies limited patches with QA while respecting AGENT policies.

### 2.2 Onboarding Task Codex (mandatory entry point)
- The onboarding process lets Codex load repository context and all governance rules (AGENTS_INDEX, local AGENTS, operational policies).
- It activates path safety, confirms that the micro-PR model applies, and establishes the SSoT.
- It runs once at the start of the Prompt Chain before any operational prompt.

### 2.3 Prompt Chain definition
- A numbered sequence of prompts (Prompt 0..N).
- Each prompt is an autonomous step with a limited scope and is handled as a micro-PR with QA.
- No batch execution: one prompt at a time.

### 2.4 Prompt Chain lifecycle

- **Kick-off**
  - The Planner decides to start a Prompt Chain.
  - Onboarding Task Codex runs as a prerequisite, ensuring Codex has loaded the SSoT, AGENT policies, and path safety rules.
  - Only after onboarding may the OCP issue Prompt 0.

- **Execution**
  - The OCP issues one prompt at a time.
  - Codex executes the prompt, applies scoped micro-PRs, and produces a unified diff plus a structured report.
- Every operational prompt must start with the "Active Rules" memo reminding teams about path safety ON, micro-PR discipline, zero side effects, documentation updates, intermediate QA (`pytest -q -k "not slow"`), final QA (`pytest -q` + `pre-commit run --all-files`), and the Italian Language Policy. Codex responses must include this memo and confirm compliance with the OCP⇄Codex turn-based cycle (OCP -> Codex response -> evaluation -> next prompt).
  - Before moving to the next prompt, execute the filtered QA `pytest -q -k "not slow"` plus any prompt-specific tests; the final prompt runs the full suite.
  - The Planner decides whether to continue, adjust direction, or start closing.

- **Closure (mandatory rule)**
  - Even if the Planner asks for an early shutdown, the OCP still issues a final QA prompt.
  - The final QA prompt aims to bring the entire repository green by running:
    ```
    pre-commit run --all-files
    pytest -q
    ```
  - If either command fails, Codex applies micro-corrections and retries (up to 10 attempts).
  - The Prompt Chain is considered complete only when both commands pass.
  - The final response must include a one-line commit summary that closes the chain.

## 3. Part B - Operational Contract for Codex

### 3.1 What is a Prompt Chain for Codex?
- A sequence of numbered prompts, each limited in scope and mapped to a micro-PR.
- Execute one prompt at a time; do not anticipate future steps or generate prompts autonomously.

### 3.2 Core rules
- Always respect path safety, atomic writes, AGENTS_INDEX + local AGENTS, this SSoT, and the local QA stack (formatters/linters/types/targeted `pytest`).
- Pre-Check Validation: Before applying any diff, confirm there are no raw `open(...)` calls, `Path` usage outside path-utils, `_private` imports or forbidden wrappers, hardcoded paths/magic strings, unstructured logging, REPO_ROOT/SSoT modifications, or non-atomic patches that conflict with the Active Rules memo. A failed pre-check halts QA, allows two autocorrections, and then requires OCP instructions.
- Micro-PR: each prompt is a focused, idempotent change set with a clear scope; run intermediate QA (`pytest -q -k "not slow"`) before proceeding, and perform the final QA (`pytest -q` + `pre-commit run --all-files`). After two failed autocorrections, request guidance from the Planner/OCP.
- All conversational exchanges between Codex, the OCP, and the user must be in Italian unless the prompt explicitly says otherwise; technical documentation may stay English.
- Edit only the files explicitly permitted by the prompt and adhere strictly to the defined scope.

### 3.3 Prompt format
- Every prompt declares purpose (1-3 lines), allowed/prohibited files, expected outputs (diff, report, QA), and explicit prohibitions.

### 3.4 Required output per prompt
- Produce a unified diff (if changes exist).
- Provide a structured report covering applied changes, impact, QA performed, and suggested next steps; mention any assumptions if the prompt was incomplete.

### 3.5 Anti-patterns
- Adding unrequired context, touching unspecified files, creating overly broad interventions, or combining unrelated domains (code + config + heavy documentation) in the same prompt.

## Codex Smoke Chain - Diagnostic Test
- **Objective:** simulate a conceptual mini-cycle (S0-S4) to confirm turn-taking, the Active Rules memo, QA policies, escalation, Italian language, and the Pre-Check validation are wired correctly, without editing the repo.
- **Structure:**
  - S0: OCP sends a toy prompt; Codex acknowledges the Active Rules memo.
  - S1: Codex explains how it would perform the Pre-Check validation on a mock diff (no files created).
  - S2: OCP issues a hypothetical operational prompt; Codex replies with a conceptual micro-PR summary.
  - S3: Codex states the intermediate QA (`pytest -q -k "not slow"`) it would run and how it would interpret the result (without executing commands).
  - S4: Codex describes the escalation path (max two autocorrections), final QA plan (`pytest -q` + `pre-commit run --all-files`), and reconfirms Italian conversation compliance.
- **Rules:** no real patches or disk writes, no QA commands executed; always respect path safety/micro-PR, and treat the Smoke Chain as a HiTL health check after any Prompt Chain update.
- **Use cases:** diagnose Prompt Chain misconfigurations, validate new meta-file updates, and demonstrate that the OCP⇄Codex orchestration remains intact.
