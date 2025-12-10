# Purpose

Operational rules for the Codex agent acting within `.codex/`, focusing on path safety, atomic writes, QA, and GitHub orchestration.



# Rules (overrides)

- Path-safety: write only within `src/`, `tests/`, `docs/`, `.codex/`; never touch `config/**`, `.env*`, `output/**`; scrivo solo in italiano per le conversazioni when referencing this perimeter.
- Atomic I/O via SSoT helpers (`ensure_within*`, `safe_write_*`), no import-time side effects.
- Standard QA pipeline: `isort`, `black`, `ruff --fix`, `mypy`, `pytest -q -k 'not slow'`.
- Use only the helper Git workflows `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease` for pushes (stubs used in `tests/pipeline/test_github_push.py`).
- Reuse vision/UI helpers `_is_gate_error` (`ui.pages.tools_check`) and the `build_payload/emit_structure` builders from `tools.gen_dummy_kb`.
- Work with the Senior Reviewer via single-scope micro-PRs, summarizing changes with references to `.codex/CONSTITUTION.md` and `docs/AGENTS_INDEX.md`, documenting QA and any open questions.
- Codex operates under the Prompt Chain defined by the OCP: every prompt is a micro-PR respecting AGENT-first/HiTL, path safety, QA, and the SSoT `docs/AGENTS_INDEX.md`. The OCP orchestrates but does not modify the repository. Refer to `docs/PromptChain_spec.md` for the full chain definition.
- Prompt Chain behavior: stop after each response, wait for the next OCP prompt, do not invent prompts 2..N autonomously; follow the turn-based contract in `docs/PromptChain_spec.md` as the single source of truth.
- Language policy: all conversational exchanges between Codex, the OCP, and the user must occur in Italian unless explicitly instructed otherwise; technical documentation may remain in English.



# Acceptance Criteria

- Path safety enforced (writes limited to `src/`, `tests/`, `docs/`, `.codex/` without exception).
- Atomic writes with no import-time side effects.
- Local QA completed via the standard pipeline.
- Micro-PR: deliver a focused change set with motivation; update related docs/tests when touching an area.
- UI messages should stay concise; save only via SSoT utilities.
- Every Prompt Chain change set must include the final QA prompt (`pytest -q` + `pre-commit run --all-files`) and the closing commit must follow the semantics in `docs/PromptChain_spec.md`.



# Riferimenti

- docs/AGENTS_INDEX.md
- .codex/CONSTITUTION.md
- .codex/WORKFLOWS.md
- .codex/CODING_STANDARDS.md
- .codex/CHECKLISTS.md
- docs/runbook_codex.md
