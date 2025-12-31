# SPDX-License-Identifier: GPL-3.0-only
## ROLE: Codex / PHASE: Closure

Purpose: formalize the closure packet (Prompt N+1) and the subsequent Skeptic Gate N+1′ that every Prompt Chain must pass before it is considered complete.

## Prompt N+1 (Closure Packet)
- role: `Codex`
- expected output:
  1. summary of changes and safety rationale,
  2. verification of policies `.codex/AGENTS.md`, `.codex/PROMPTS.md`, `.codex/WORKFLOWS.md`,
  3. list of automated tests executed + Skeptic Gate log,
  4. mandatory commit info:
     - commit subject (ITA)
     - short commit id
     - full commit SHA
     - SHA actually pushed
  5. closing note “Chain closed” in Italian.

### Push policy (parameterized)
- Push (branch or `main`) is governed by `DELIVERY STRATEGY` declared in Prompt 0.
- Push is **not default**: it happens only in Prompt N+1, only with explicit OCP authorization in Prompt N+1, and only if final QA is PASS.
- PASS of Skeptic Gate N+1′ formally closes the chain (post N+1); it is not a runtime prerequisite to execute the push within N+1.

## Skeptic Gate N+1′
- role: `OCP`
- verification: diff against base branch, guardrails on sensitive files (`src/ai/resolution.py`, `pipeline/exceptions.py` etc.), patterns `Optional`, `return None`, `ConfigError`.
- does not implement: new logic, architectural refactors, timeline negotiations.

- [ ] Scope confirmed (target files checked)
- [ ] Evidence verified (log/test/pattern)
- [ ] UX invariants confirmed (messages unchanged, ConfigError compatible)
- [ ] Declared vs actual guardrails documented (SKEPTIC_ACK.md or updated tests)
- [ ] Realistic risks enumerated
- [ ] Rollback strategy ready

## Outcomes
- PASS → Prompt Chain closed.
- PASS WITH CONDITIONS → not closed; requires a new Prompt N+1 before merge.
- BLOCK → HiTL required.

## Binding rule
A Prompt Chain is closed only after PASS of Skeptic Gate N+1′.

## Riferimenti
- `.codex/PROMPTS.md`
- `.codex/WORKFLOWS.md`
- `.codex/AGENTS.md`
- `system/ops/runbook_codex.md`
- `system/specs/promptchain_spec.md` (SSoT)
- `SKEPTIC_ACK.md`

## ACK / skip note
The Skeptic Gate can be ACKed by updating `tests/**` or `SKEPTIC_ACK.md`. If diff context is missing (e.g., local run) the gate prints “SKIPPED”.
