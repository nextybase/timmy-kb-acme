# NeXT Principles & Probabilismo (minimum)

- Human-in-the-Loop: agents propose solutions, the team decides. Keep iterations short and verifiable.
- Probabilism: decisions rely on evidence (tests, metrics, logs). Update rules when the data changes.
- Consistency: a single source of truth for paths/I-O (SSoT) and for tags (SQLite at `semantic/tags.db`).
- Safety: no writes outside the customer perimeter; redact secrets in logs.
- Portability: support both Windows and Linux; pay attention to encodings and paths (POSIX vs Windows) when exchanging files.

## Prompt Chain Governance
- Each intervention by Codex passes through the Prompt Chain model: Phase 0 (analysis/read-only), Phase 1..N (micro-PR operations), Prompt N+1 (final QA + summary).
- The turn-based protocol Planner → OCP → Codex → OCP → Planner ensures at most one action per prompt and mandates Italian-only replies from Codex while documentation remains English.
- Prompt Chain prompts follow the Active Rules memo (path safety, zero side effects, Active Rules, language policy, QA) defined in `.codex/PROMPTS.md`; the final QA prompt runs `pre-commit run --all-files` and `pytest -q`.
- The constitution defers to `system/specs/promptchain_spec.md`, `system/ops/runbook_codex.md`, `.codex/PROMPTS.md` and `.codex/CHECKLISTS.md` as complementary SSoT references for the contract.
