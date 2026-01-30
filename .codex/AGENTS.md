# Purpose

Operational rules for the Codex agent acting within `.codex/`, focusing on path safety, atomic writes, and QA.



# Rules (overrides)

- Path-safety: scrivo solo in `src/`, `tests/`, `docs/`, `.codex/`.
  - **Default rule:** writing outside these paths is **prohibited**.
  - **User-authorized exception:** writing outside these paths is allowed **only** if the **user explicitly authorizes a specific exception** (scope + target paths + rationale) in the current prompt/thread. The exception must be documented in the micro-PR summary (including what was authorized and where).
  - Limited standing exceptions (still require "documentation-only/no logic" constraints):
    - `tools/dummy/**` and `tools/smoke/**` **only** for standardized confinement headers/docstrings (documentation-only, no logic).
    - `tools/ai_checks/**` for CLI diagnostics (no runtime/UI imports).
  - Never touch `config/**`, `.env*`, `output/**` unless explicitly authorized by the user exception (and still discouraged).
- Atomic I/O via SSoT helpers (`ensure_within*`, `safe_write_*`); no import-time side effects.
- Standard QA pipeline: `isort`, `black`, `ruff --fix`, `mypy`, `python tools/test_runner.py fast`.
- Reuse vision/UI helpers `_is_gate_error` (`ui.pages.tools_check`) and the `build_payload/emit_structure` builders from `tools.gen_dummy_kb`.
- Work with the Senior Reviewer via single-scope micro-PRs, summarizing changes with references to `.codex/CONSTITUTION.md` and `system/ops/agents_index.md`, documenting QA and any open questions.
- Codex operates under the Prompt Chain defined by the OCP: every prompt is a micro-PR respecting AGENT-first/HiTL, path safety, QA, and the SSoT `system/ops/agents_index.md`. The OCP orchestrates but does not modify the repository. Refer to `system/specs/promptchain_spec.md` and `.codex/PROMPTS.md` for the full chain definition, the phase model (Phase 0 analytical/read-only, Phase 1..N operational micro-PRs, Prompt N+1 final QA), and the template requirements.
- Prompt Chain behavior: stop after each response, wait for the next OCP prompt, and do not invent future prompts; Phase 0 prompts never change files or launch QA, Phase 1..N prompts are the only ones allowed to produce diffs and run `python tools/test_runner.py fast`, and Prompt N+1 runs `pre-commit run --all-files` + `pre-commit run --hook-stage pre-push --all-files` (fallback: `python tools/test_runner.py full`) before finalizing the chain.
- Language policy: conversations are Italian by default; when the OCP declares control-mode, OCP <-> Codex switches to English; Timmy/ProtoTimmy <-> User remains Italian. Technical documentation may remain in English.



# Acceptance Criteria

- Path safety enforced (writes limited to `src/`, `tests/`, `docs/`, `.codex/` by default; any deviation requires explicit user authorization and must be documented).
- Atomic writes with no import-time side effects.
- Local QA completed via the standard pipeline.
- Micro-PR: deliver a focused change set with motivation; update related docs/tests when touching an area.
- UI messages should stay concise; save only via SSoT utilities.
- Every Prompt Chain change set must include the final QA prompt (`pre-commit run --all-files` + `pre-commit run --hook-stage pre-push --all-files`, fallback: `python tools/test_runner.py full`) run during Prompt N+1 and the closing commit must follow the semantics (Italian one-line summary) described in `system/specs/promptchain_spec.md`.



# References

- system/ops/agents_index.md
- .codex/CONSTITUTION.md
- .codex/WORKFLOWS.md
- .codex/CODING_STANDARDS.md
- .codex/CHECKLISTS.md
- system/ops/runbook_codex.md
