# Purpose

Operational rules for the Codex agent acting within `.codex/`, focusing on path safety, atomic writes, and QA.



# Rules (overrides)

- Path-safety: write only within `src/`, `tests/`, `docs/`, `.codex/`; **eccezione limitata**: `tools/dummy/**` e `tools/smoke/**` **solo** per header/docstring standardizzati di confinamento (documentazione-only, nessuna logica); never touch `config/**`, `.env*`, `output/**`; scrivo solo in italiano salvo eccezione control-mode OCP -> Codex in inglese.
- Atomic I/O via SSoT helpers (`ensure_within*`, `safe_write_*`), no import-time side effects.
- Standard QA pipeline: `isort`, `black`, `ruff --fix`, `mypy`, `pytest -q -k 'not slow'`.
- Reuse vision/UI helpers `_is_gate_error` (`ui.pages.tools_check`) and the `build_payload/emit_structure` builders from `tools.gen_dummy_kb`.
- Work with the Senior Reviewer via single-scope micro-PRs, summarizing changes with references to `.codex/CONSTITUTION.md` and `system/ops/agents_index.md`, documenting QA and any open questions.
- Codex operates under the Prompt Chain defined by the OCP: every prompt is a micro-PR respecting AGENT-first/HiTL, path safety, QA, and the SSoT `system/ops/agents_index.md`. The OCP orchestrates but does not modify the repository. Refer to `system/specs/promptchain_spec.md` and `.codex/PROMPTS.md` for the full chain definition, the phase model (Phase 0 analytical/read-only, Phase 1..N operational micro-PRs, Prompt N+1 final QA), and the template requirements.
- Prompt Chain behavior: stop after each response, wait for the next OCP prompt, and do not invent future prompts; Phase 0 prompts never change files or launch QA, Phase 1..N prompts are the only ones allowed to produce diffs and run `pytest -q -k "not slow"`, and Prompt N+1 runs `pre-commit run --all-files` + `pytest -q` before finalizing the chain.
- Language policy: conversations are Italian by default; when the OCP declares control-mode, OCP ↔ Codex switches to English; Timmy/ProtoTimmy ↔ User remains Italian. Technical documentation may remain in English.



# Acceptance Criteria

- Path safety enforced (writes limited to `src/`, `tests/`, `docs/`, `.codex/` without exception).
- Atomic writes with no import-time side effects.
- Local QA completed via the standard pipeline.
- Micro-PR: deliver a focused change set with motivation; update related docs/tests when touching an area.
- UI messages should stay concise; save only via SSoT utilities.
- Every Prompt Chain change set must include the final QA prompt (`pytest -q` + `pre-commit run --all-files`) run during Prompt N+1 and the closing commit must follow the semantics (Italian one-line summary) described in `system/specs/promptchain_spec.md`.



# Riferimenti

- system/ops/agents_index.md
- .codex/CONSTITUTION.md
- .codex/WORKFLOWS.md
- .codex/CODING_STANDARDS.md
- .codex/CHECKLISTS.md
- system/ops/runbook_codex.md
