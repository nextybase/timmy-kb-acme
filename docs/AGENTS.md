# docs AGENTS

## Scope & Primary Reader
- Folder scope: human-facing guides in Italian (`docs/`).
- Primary reader: contributors and subject-matter experts updating usage, UI, developer, or policy guidance.

## Authority & Precedence
- Governance, lifecycle, and HiTL contracts reside in `instructions/*`. This folder provides clarifications, localized narratives, and examples only.
- Do not override the agency statements in `instructions/00_ssot_agency.md`; cite them when referencing prompt chain behavior.
- This file is a folder-level engagement guardrail, not an exhaustive entrypoint catalog; refer to `system/architecture.md` for repo→flow mapping.

## Change Policy
- Allowed changes: clarity edits, formatting, typos, link refinements, screenshots, additional references to supporting docs.
- Forbidden changes: introducing new governance statements, allowed-action tables, lifecycle phases, or preferences not already approved.
- If a PR touches agency, Prompt Chain, or HiTL content here, STOP and escalate to OCP for explicit approval before editing this file.

## Required Evidence for Changes
- Each update must reference the doc(s) it refines, include a short rationale (why the clarification is needed), and show that prompts/tests still pass (`pre-commit`, `cspell`).
- Provide links to `system/` or `instructions/` entries when quoting workflow behavior.

## Codex Engagement Rules
- Codex may edit `docs/` files only when the prompt explicitly targets `docs/` via TARGET FILES or declares a documentation-focused INTENT, and supporting proofs (screenshots, flow references, QA results) are provided.
- Always obey the `Prompt Chain` plan before editing; do not add new governance clauses in this folder.
