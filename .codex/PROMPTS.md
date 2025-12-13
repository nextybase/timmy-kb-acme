# Prompt Chain Operational API

## Turn-Based Protocol & Single-Turn Execution
- Planner → OCP → Codex → OCP → Planner is the only valid sequence; each prompt must contain exactly one action and never bundles multiple turns.
- OCP issues prompt numbers in order; after Codex replies, the cycle pauses until the next OCP instruction (no autopilot beyond the current prompt).
- Prompts 0/0a..0x remain analytical/read-only, prompts 1..N are operational micro-PRs, and prompt N+1 finalizes the chain with full QA.
- The Onboarding Task Codex sets this protocol before any edits can happen, so its acknowledgement is mandatory in Prompt 0.

## Language Policy for Codex
- All codified documents and templates stay in English to preserve the SSoT grammar.
- Codex responses must always be written in Italian within every prompt of the chain unless an explicit exception is granted in a prompt.
- This policy covers narrative reports, QA summaries, and communication with Planner/OCP.

## Prompt Template Requirements
- Templates below are the only structures permitted; every prompt must state its purpose, phase, allowed files, Active Rules memo, and expected outputs.
- Operational prompts (1..N) exclusively produce diffs, touch files, and run intermediate QA (`pytest -q -k "not slow"`). Phase 0 prompts stay analytical and perform no edits, while prompt N+1 runs the full QA suite plus final narration.
- Every prompt must be supplied as a single copyable block listing Role, Phase, Scope (allowed/prohibited files), Active Rules memo, Expected Outputs (diff + structured report + QA), Tests executed, Constraints, and Stop Rules to keep instructions unambiguous.
- **If a prompt expects any file change, it must explicitly request a unified diff and a structured report in the “Expected Outputs” section.** Codex must not treat a change as “done” without those artifacts.

### Template: Prompt 0
- Purpose: define the final goal of the Prompt Chain, the high-level plan, and instruct Codex to ingest the SSoT.
- Required actions: load `docs/coding_rule.md`, `docs/developer_guide.md`, `docs/PromptChain_spec.md`, `.codex/AGENTS.md`, `.codex/CODING_STANDARDS.md`, `.codex/WORKFLOWS.md`, `.codex/CHECKLISTS.md`, and `.codex/PROMPTS.md`, then confirm comprehension.
- Mode: analytical, read-only; no files changed, no QA commands executed.
- Output: Italian summary of the plan, statement of loaded documents, and risks.

### Template: Prompt 0a..0x
- Purpose: refine the plan with deeper analysis, file-by-file mapping, and sequencing of upcoming prompts.
- Mode: analytical/read-only; still no edits or QA.
- Output: Italian reasoning for each mandated document, points of ambiguity, proposed sequence for prompts 1..N, and explicit confirmation that no files or tests were touched.

### Template: Prompt 1..N
- Purpose: deliver operational micro-PRs that implement the scoped changes declared by the OCP.
- Mandatory sections: purpose statement, phase identifier, allowed/prohibited files, Active Rules memo (with path safety, micro-PR scope, intermediate QA requirements, Italian language reminder), expected outputs (diff + structured report + intermediate QA results), dependencies, and tests executed.
- Action: apply a diff, document the behavior change in the report, run `pytest -q -k "not slow"` (or a justified substitute) and describe the result; mention whether additional linters/types were run.
- Language: the entire response must be in Italian.
- Push requirement: explicitly declare in the structured block whether a push to `main` is requested by the OCP; without that statement, Codex assumes no push occurs (pushes are reserved for Prompt N+1 or when OCP explicitly authorizes them).
- **Diff requirement:** the structured block must always request and include a unified diff for files touched in this step.

### Template: Prompt N+1
- Purpose: conclude the chain via final QA and a closing narrative.
- Mandatory content: QA results for `pre-commit run --all-files` and `pytest -q`, documentation of retries/micro-fixes (up to ten attempts), full summary of the chain’s work, and the one-line closing commit message in Italian (unless otherwise specified).
- Action: only after both QA commands succeed may the chain be considered complete; Codex must report any remaining issues before ending.

## Active Rules Memo
- Begin every operational response (Prompt 1..N) with the Active Rules memo that reminds the team about path safety ON, micro-PR focus, zero side effects, documentation updates, intermediate QA (`pytest -q -k "not slow"`), final QA (`pytest -q` + `pre-commit run --all-files`), and the Italian language policy referenced in `docs/PromptChain_spec.md`.
- Confirm compliance with the turn-based protocol inside each memo.

## Prompt Chain Operational Contract
The Prompt Chain operational contract spells out the dialogue model between the OCP and Codex and requires Codex to act idempotently, attentively, and aligned with the policies documented in `docs/runbook_codex.md`, `docs/codex_integrazione.md`, and `docs/PromptChain_spec.md`. Every prompt must be treated as an independent micro-PR with a fixed scope and no unauthorized creative deviations.
- Always answer only one prompt at a time: after you reply, halt execution, wait for the next OCP prompt, and never invent additional prompts.
- Do not design new architectures, refactors, or self-initiatives beyond the OCP's explicit requirements; stay within the provided scope.
- Observe the "idempotent micro-PR" rule: keep changes minimal, mentally reversible, and free of import-time side effects.
- Remember that `docs/PromptChain_spec.md` is the SSoT for the Prompt Chain and that `docs/runbook_codex.md`/`docs/codex_integrazione.md` describe the operational context.

## Startup Tasks
- Read `docs/AGENTS_INDEX.md`, `.codex/AGENTS.md`, `.codex/CODING_STANDARDS.md`, and `docs/runbook_codex.md`.
- Use only SSoT utilities (`ensure_within*`, `safe_write_*`); restrict writes to `src/`, `tests/`, `docs/`, `.codex/`.

## Path Safety Hardening and Atomic Writes
- Replace manual joins with `ensure_within_and_resolve`.
- Apply atomic `safe_write_text/bytes` calls with slug/perimeter guards.
- Add unit tests for traversal/symlink handling and out-of-perimeter paths.

## GitHub Orchestration (required helpers)
- Use `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`.
- Stub `_prepare_repo`/`_stage_changes` in tests as shown in `tests/pipeline/test_github_push.py`.
- Emit structured logs for the flow (`prepare_repo`, `stage_changes`, `push`).

## Micro-PR Template
Title: <brief, imperative>
Motivation: <bugfix/security/robustness; impact>
Scope: <files touched and why; single change set>
Rules honored: path safety / atomicity / no import-time side effects
Tests: <new/updated; e.g., pytest -k ...>
QA: isort  black  ruff --fix  mypy  pytest
Docs notes: <if you touch X, update Y/Z>

## Active Rules for Operational Prompts
- Active Rules: path safety ON, micro-PR discipline, zero side effects, documentation updates when functionality changes, intermediate QA (`pytest -q -k "not slow"`), final QA (`pytest -q` + `pre-commit run --all-files`), and the Language Policy for Italian conversations.
- After Prompt 0/1, OCP issues one prompt at a time, Codex responds with diff/report/QA, OCP evaluates, and only then emits the next prompt; never stack multiple OCP prompts without a Codex reply.
- Include this memo at the start of every operational response to reinforce the OCP⇄Codex turn cycle and remind that each step is a narrow micro-PR with mandatory intermediate QA.
- Micro-PR + QA: apply focused changes, run `pytest -q -k "not slow"` before moving on, document tests and retries, and perform the full final QA run plus `pre-commit run --all-files` at the concluding prompt.
- Escalation: after two failed correction attempts during intermediate or final QA, ask the OCP/user for instructions before proceeding.

## Patch Pre-Check Validation
- Before generating or applying any patch, run a static pre-check: ensure the diff avoids raw `open(...)` calls, `Path` usage without safe path-utils, raw file writes, imports from `_private` or forbidden wrappers, hardcoded directories or magic strings, unstructured logging, and modifications to REPO_ROOT/SSoT.
- Verify the diff remains atomic, limits changes to the scoped objective, and does not introduce unplanned refactors or semantic ambiguity relative to the "Active Rules" memo.
- If the pre-check fails, halt before QA, rewrite the patch using safe-write utilities and path safety, and attempt corrections up to twice; after the third failure, pause and request new instructions from the OCP.

## Error Handling in the Prompt Chain
- Keep error handling transparent and coordinated with the OCP: document anomalies, avoid infinite loops, and seek guidance when needed.
- Always report the current state, outputs, and steps already attempted so the OCP can make informed decisions.
- If the same issue (test or stack trace) repeats more than twice in a single step, stop, log the attempts, and confirm the next action with the OCP.
- Do not proceed until the following prompt arrives; disclose how many iterations you have exhausted.
- Every operational prompt (except the final one) must state that it ran `pytest -q -k "not slow"` (plus any additional tests requested); record retries and outcomes before continuing.
- The final QA cycle (`pytest -q` + `pre-commit run --all-files`) follows the thresholds in `docs/PromptChain_spec.md`; avoid divergent retry counts, keep retries reasonable, and describe each rerun explicitly.

## Using Tests in the Prompt Chain
- Test execution is scoped per prompt, with two distinct phases: optional tests when requested and mandatory closing QA.
- Run only the commands explicitly enumerated in the prompt, and explain which tests were executed and why.
- Each intermediate prompt must include the standard QA `pytest -q -k "not slow"` (and any additional targeted tests); the final prompt executes the full suite without filtering.
- The closing prompt always runs `pytest -q` and `pre-commit run --all-files` (per `docs/PromptChain_spec.md` and `docs/runbook_codex.md`); if they fail, apply minimal fixes and rerun until both succeed.
- Document failed tests or repeated retries in your final reply, specifying the fixes and the number of attempts.

## Commits and Pushes in the Prompt Chain
- Codex proposes patches, waits for confirmation, and never pushes autonomously: the final commit must follow the semantics in `docs/PromptChain_spec.md`.
- Present the diff, request human/OCP confirmation, and do not perform commit/push before full validation.
- Pushes happen only after QA completes (`pytest -q`, `pre-commit run --all-files`) and with explicit approval from the OCP or responsible human.
- The closing Prompt Chain commit must state that the chain is sealed, summarize QA/tests, and notify the OCP of next steps or outstanding issues.

## Turn-Based Prompt Chain (OCP→Codex Cycle)
- **SSoT:** refer to `docs/PromptChain_spec.md` for governance and the operational contract.
- The OrchestratoreChainPrompt (OCP) issues numbered prompts (Prompt 0, 1, 2, ...); each stays within a fixed scope and corresponds to a micro-PR under the same Codex rules (HiTL, AGENT-first, QA, path safety, atomic I/O).
- The OCP never edits the repository; it converts Timmy/ProtoTimmy's goals into formal prompts and drives Codex one step at a time. Codex must not anticipate future steps, generate additional prompts, or expand the defined scope.
- The Onboarding Task Codex remains the required entrypoint: it enforces scope, prohibits touching unrequested files, and ensures idempotent, traceable outputs per prompt.

## Onboarding Task Codex
- Read the three SSoT documents before making edits: `docs/AGENTS_INDEX.md`, the relevant area `AGENTS.md`, and `.codex/AGENTS.md`.
- Propose a concise action plan (steps and order) before modifying files.
- Apply the micro-PR model: single scope, minimal diff, idempotent, and clearly motivated.
- QA checklist: path safety via SSoT utilities, scoped writes, atomic logging; keep the AGENTS matrix updated when touching `AGENTS.md`, refresh documentation if behavior changes, and honor area-specific overrides.

## Codex Smoke Chain - Diagnostic Test
- **Goal:** verify that the Prompt Chain respects turn-taking, memo recognition, QA rules, escalation limits, the Italian Language Policy, and the Pre-Check validation without editing the repository.
- **Structure:** S0: OCP issues a minimal prompt; Codex confirms that the Active Rules memo is recognized. S1: Codex describes how it would run the Pre-Check validation on a mock diff (no files created). S2: OCP simulates an operational prompt; Codex replies with a conceptual micro-PR description. S3: Codex articulates the intermediate QA (`pytest -q -k "not slow"`) it would run and explains how it would interpret outcomes (without executing anything). S4: Codex summarizes the escalation/retry plan, final QA (`pytest -q` + `pre-commit run --all-files`), and reconfirms Italian-language compliance.
- **Rules:** no actual patches, no disk writes, no QA commands executed; perform the entire chain conceptually as a fast diagnostic after modifying Prompt Chain metadata.
- **Use cases:** diagnose governance issues, validate Prompt Chain updates, and provide HiTL evidence that the OCP→Codex cycle, QA policies, Pre-Check validation, and Italian-language policy remain synchronized.

# Semantics & tags.db

## Startup tasks
- Read `docs/AGENTS_INDEX.md` and `src/semantic/AGENTS.md`.
- Ensure `semantic/tags.db` exists; treat `tags_reviewed.yaml` as a human authoring checkpoint.

## Enrichment front matter
- Use `semantic.api` (avoid `_private`); treat `tags.db` as the SSoT for canonical tags.
- If `tags.db` is missing, propose a safe migration/regeneration (no silent fallback).
- Generate README/SUMMARY files via repository utilities with idempotent fallbacks.

## Facade vs services alignment
- Confirm signature parity between `semantic.api` and services (`convert/frontmatter/embedding`).
- Add compatibility tests and alias/synonym coverage for tags.

# UI Streamlit

## Startup tasks
- Read `docs/streamlit_ui.md`, `src/ui/AGENTS.md`, and `src/ui/pages/AGENTS.md`.
- Verify RAW/slug gating, the `st.Page` + `st.navigation` router, and import safety (no I/O during import).

## Router and onboarding gating
- Enforce native routing (`st.navigation(pages).run()`), using internal links through `st.page_link`.
- Semantics gating: enable the Semantica tab only after `raw/` exists; keep user messages short and log details.
- Manage state and slug with `ui.utils.route_state` and `ui.utils.slug`; avoid query tricks.

## Deprecation sweep and layout
- Remove `st.cache`, `st.experimental_*`, `unsafe_allow_html`, and `use_container_width`.
- Keep layouts stub-friendly (avoid unsupported `with col` blocks); prefer `st.dialog` with fallbacks.
- Log via `get_structured_logger("ui.<page>")`; avoid `print()` and PII leaks.

# Test & QA

## Startup tasks
- Read `docs/AGENTS_INDEX.md` and `tests/AGENTS.md`.
- Prepare dummy datasets; avoid network dependencies by mocking Drive/Git.

## QA pipeline
- Run `isort`, `black`, `ruff --fix`, `mypy`, and `pytest -q -k 'not slow'` (for intermediate prompts).
- The final QA prompt instead runs `pytest -q` (without filters) and `pre-commit run --all-files`.
- Include contract tests for the `book/` guard (only `.md`, ignore `.md.fp`) and smoke E2E runs on dummy slugs.

# Docs & Runbook

## Startup tasks
- Read `docs/runbook_codex.md`, `docs/AGENTS_INDEX.md`, and `docs/AGENTS.md`.
- Keep front matter/titles aligned with `v1.0 Beta` and maintain cSpell checks on `docs/` and `README.md`.

## Doc sync (API or flow changes)
- Align the code with `docs/architecture.md`, `docs/developer_guide.md`, and `docs/guida_ui.md`.
- Apply minimal patches; update `.codex/WORKFLOWS.md` if the flow changes.
- Verify cSpell and relative links.

## cSpell cleanup on docs/
- Gather unknown words; update `cspell.json`/`.vscode/settings.json` only for domain-specific terms.
- Avoid ignoring entire files.

## Senior Reviewer request
- Deliver: concise title, context, files touched + changes, QA results (formatter/linter/type/test), missing tests/known issues, and 2-3 questions for the Senior.
- Respect `.codex/CONSTITUTION.md`, `.codex/AGENTS.md`, and `docs/AGENTS_INDEX.md`; keep the scope to a micro-PR.
