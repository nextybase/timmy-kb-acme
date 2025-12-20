# instructions AGENTS

## Scope & Primary Reader
- Folder scope: governance SSoT living in `instructions/*`.
- Primary reader: agents (Codex/OCP) and governance maintainers orchestrating the Prompt Chain.

## Authority & Precedence
- This folder defines agency roles, lifecycle phases, allowed actions, HiTL triggers, and the Work Order Envelope. No other path may override these rules.
- Any mention of control plane decisions, gatekeepers, or allowed actions outside this folder must cite the relevant `instructions/*` section.

## Change Policy
- Only micro-edits (typos, clearer terminology, formatting) are allowed, and then only when explicitly requested by OCP.
- Forbidden without explicit approval: changes to roles, phases, allowed actions, HiTL coverage, or the canonical Prompt Chain sequence.

## Required Evidence for Changes
- Every edit must include: rationale, impacted sections, and a cross-reference check against dependent docs (e.g., `system/ops/runbook_codex.md` or `docs/index.md`).
- Document associated verification steps (link check, lint, prompt plan) before merging.

## Codex Engagement Rules
- Codex should respond with NEED_INPUT when asked to modify governance semantics unless the prompt cites the explicit approval clause.
- Any change must mention the specific Prompt Chain phase or section area affected; aim for traceable, minimal adjustments to maintain the SSoT.
