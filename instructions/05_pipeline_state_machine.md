# Pipeline State Machine — v1.0

## Scope & Non-goals
- Defines the normative foundation pipeline states that produce semantically enriched markdown and the validated knowledge graph.
- Non-goal: implementation details, CLI commands, or UI flow descriptions.

## Agency & Lifecycle Relationship
- Pipeline completion (enriched markdown + validated knowledge graph) is the sole condition for transitioning agency from ProtoTimmy to Timmy.
- Lifecycle phases (PLANNING → MICRO_PLANNING → VALIDATION → EXECUTION → QA → CLOSURE) orchestrate decision flow; pipeline states track artefact readiness.

## Pipeline States
| State | Entry | Required Artefacts | Allowed Actions (family) | Exit |
|-------|------|--------------------|-------------------------|------|
| `WORKSPACE_BOOTSTRAP` | intent registered, prompt includes workspace slug | raw/, config/, semantic/ directories created via WorkspaceLayout | `REGISTER_*`, `VALIDATE_*` (config/schema checks) | Gatekeepers confirm workspace, move to `SEMANTIC_INGEST` |
| `SEMANTIC_INGEST` | workspace present, raw artefacts available | raw PDFs, `config/config.yaml`, `tags_reviewed.yaml` (if advisory) | `VALIDATE_*`, `GENERATE_*` (metadata export) | Tag/semantic Gatekeepers confirm `tags.db` updates, proceed to `FRONTMATTER_ENRICH` |
| `FRONTMATTER_ENRICH` | `tags.db` / semantic mapping exists | enriched frontmatter (`book/*.md`), `README.md`, `SUMMARY.md` drafts | `VALIDATE_*` (frontmatter, semantic index checks) | Gatekeepers verify frontmatter/embedding logs, move to `VISUALIZATION_REFRESH` |
| `VISUALIZATION_REFRESH` | frontmatter validated | final README/SUMMARY + preview artefacts (`semantic/kg.tags.*`) | `GENERATE_*` (preview docs, vision statements) | Gatekeepers/OCP verify `semantic/kg.tags.*`, proceed to `PUBLISH_PREP` |
| `PUBLISH_PREP` | previews approved, GitHub/Drive configuration ready | `book/`, `semantic/` artefacts staged | `EXECUTE_*` (push, publish) under Work Order Envelope | Stop or complete; upon success (validated artifacts + KG) pipeline complete |

## State Transitions
- `WORKSPACE_BOOTSTRAP` → `SEMANTIC_INGEST`: triggered when raw+config artefacts exist and Gatekeepers log `semantic.book.frontmatter` start.
- `SEMANTIC_INGEST` → `FRONTMATTER_ENRICH`: occurs when `semantic/tags.db` and mapping pass validation; evidence: `semantic.index` events + `semantic.book.frontmatter`.
- `FRONTMATTER_ENRICH` → `VISUALIZATION_REFRESH`: requires `SUMMARY.md`, `README.md` drafts plus `semantic/kg.tags.*`.
- `VISUALIZATION_REFRESH` → `PUBLISH_PREP`: Gatekeeper/OCP confirmation that vision mapping + artifact logs match expected outputs.
- Transition to `COMPLETE` (ProtoTimmy → Timmy): pipeline complete once enriched markdown + validated KG exist.

## Stop Conditions & Resume Rules
- `malformed_artifact`: owner Gatekeeper, stop_code `ContractError`, action: regenerate inputs; resume_phase `VALIDATION`.
- `unsupported_action`: owner Gatekeeper/OCP, stop_code `HITL_REQUIRED`, action: revise Work Order; resume_state previous state, phase unchanged.
- `hiTL_block`: owner OCP, stop_code `HITL_REQUIRED`, action: explicit human ack and `_should_proceed` reset; resume_state same as halted state.
- `missing_inputs`: owner Gatekeeper, stop_code `ContractsError`, action: supply missing artefacts; resume_state same state, phase `VALIDATION`.

## Agency Switch Invariant
- Until pipeline complete (enriched markdown + validated knowledge graph), ProtoTimmy governs. After those artefacts exist, Timmy assumes agency, but gatekeepers and OCP continue to enforce stops.

## Anti-confusion Rules
- Pipeline ≠ Prompt Chain: pipeline states describe artefact readiness; lifecycle phases describe decision flow.
- Pipeline state ≠ lifecycle phase: same state may span multiple phases when validation loops occur.
- Artefact readiness ≠ decision approval: only gatekeepers/Timmy release progress, not artifact existence alone.

## Completion Checklist
- [ ] Raw + config directories created (`WORKSPACE_BOOTSTRAP`).
- [ ] Semantic artefacts validated (`SEMANTIC_INGEST`, `FRONTMATTER_ENRICH`).
- [ ] Vision/document preview artefacts produced (`VISUALIZATION_REFRESH`).
- [ ] Push/artifact publication executed under Work Order Envelope (`PUBLISH_PREP`).
- [ ] Enriched markdown + validated KG exist, enabling ProtoTimmy → Timmy transition.
