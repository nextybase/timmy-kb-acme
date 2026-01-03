# docs/AGENTS

## Purpose (Read first)

This folder exists to **provide information**.

If you are an agent or contributor reading files under `docs/`, your primary task is to
**understand how Timmy-KB works, how it should be used, and how it is governed**.

This file does not define the system itself.
It defines **how to interact with documentation safely and correctly**.

---

## Where to start (Authoritative reading order)

To understand Timmy-KB correctly, always begin with:

1. `docs/index.md`
   → documentation map and recommended reading paths

2. `README.md`
   → system identity, scope, and framing

3. `MANIFEST.md`
   → epistemic limits, responsibility, and non-autonomy

4. `instructions/*`
   → governance, agency, Human-in-the-Loop, and Prompt Chain contracts

Files in `docs/` **explain and support** these sources; they do not override them.

---

## Scope & Primary Reader

- Folder scope: human-facing guides in Italian (`docs/`)
- Primary readers:
  - contributors updating usage, UI, developer, or policy documentation
  - agents gathering context to reason about the system

This folder contains **explanations, guides, and technical references**, not governance rules.

---

## Authority & Precedence

- Governance, lifecycle, and HiTL contracts live in `instructions/*`
- This folder provides:
  - localized narratives
  - clarifications
  - examples
  - operational explanations
 - Precedence order: `MANIFEST.md` -> `instructions/*` -> code -> `docs/` (incl. `docs/policies/`)

Do **not** override or reinterpret agency statements defined in:
- `instructions/00_ssot_agency.md`
- related Prompt Chain contracts

When describing agent behavior, always **cite or link** the authoritative source.

---

## Change Policy (for contributors and agents)

Allowed changes:
- clarity improvements
- formatting and typos
- link updates
- screenshots or examples
- references to existing docs

Forbidden changes:
- introducing new governance statements
- defining allowed actions or lifecycles
- altering agency boundaries or HiTL rules
- adding preferences or behavior not already approved

If a change touches **agency, Prompt Chain logic, or HiTL behavior**, stop and escalate to OCP
before editing documentation.

---

## Evidence & Traceability

Each documentation update should:
- reference the document it refines
- include a short rationale (why clarification is needed)
- preserve passing checks (`pre-commit`, `cspell`, etc.)

When describing workflows, provide links to:
- `system/`
- `instructions/`

---

## Codex / Agent Engagement Rules

Agents may edit files under `docs/` only when:
- the prompt explicitly targets documentation
- the intent is informational or editorial
- no new governance or agency rules are introduced

Always follow the declared Prompt Chain plan.
This folder is **informational**, not normative.
