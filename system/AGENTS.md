# system AGENTS

## Scope & Primary Reader
- Folder scope: system-facing documentation, specs, and operational runbooks under `system/`.
- Primary reader: agents, operators, and developers operating environments or reviewing architecture flows.

## Authority & Precedence
- Governance contracts live in `instructions/*`; system docs describe HOW, tools, and operational checks.
- Never encode new lifecycle, HiTL, or allowed-action decisions here; always cite `instructions/*` when referencing decision authority.

## Change Policy
- Allowed updates: structural clarifications, link/path corrections (with repo paths), architecture/ops mapping adjustments, and evidence-backed tooling notes.
- Forbidden edits: redefining Domain Gatekeepers, Control Plane behavior, or Work Order Envelope semantics without instructions/ authorization.
- STOP rule: If a requested change introduces or modifies governance semantics, halt immediately and request explicit OCP approval before editing under `system/`.

## Required Evidence for Changes
- Tie each change to concrete repo artifacts (e.g., `system/architecture` references, CLI entrypoints, repo paths) and include link verification outputs when moving docs or updating references.
- Document what CI/test was run if the edit affects operational sequences.

## Codex Engagement Rules
- Codex may edit only with prompts targeting system maintenance or architecture updates; mention the affected path and provide references to `instructions/*` whenever governance is mentioned.
- Avoid rewriting normative text; focus on operational accuracy and coordinate with OCP for anything beyond link/structure fixes.
