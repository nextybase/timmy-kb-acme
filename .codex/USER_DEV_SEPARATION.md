# SPDX-License-Identifier: GPL-3.0-only
## Purpose
Document the 1.0 Beta split between the **User channel** (Streamlit screens plus the surface they expose) and the **Dev channel** (CLI, tools, API, internal services). This SSoT explains who may touch each surface, where the canonical entrypoints live, and how imports must flow so the UI remains a _consumer-only_ surface while the Dev channel drives automation.

## Definitions
- **User channel**: everything under `src/ui/**` together with approved facades under `src/ui/services` (e.g. `vision_provision`, `drive_runner`). The User channel drives Streamlit flows and relies on UI guards (safe inputs, session-state, telemetry).
- **Dev channel**: automation entrypoints (typical CLI/tools) in `python -m timmy_kb.cli.*`, `tools/*`, `src/api/*` plus any scripts under `src/timmy_kb/cli`. Dev consumers may talk to UI facades when reusing logic, but they operate headless and must keep compatibility with CLI patterns.

## Canonical Entrypoints
- **User**: `src/ui/**` screens (pages, components) and `ui.services.*` facades that expose safe APIs such as `vision_services.provision_from_vision_with_config` or `drive_runner.ensure_drive_minimal_and_upload_config`. Any Streamlit page must import only these facades plus pipeline/core libs.
- **Dev**: modules under `src/timmy_kb/cli/*`, `tools/*`, `src/api/*`, `src/pipeline/capabilities/*`, `src/ai/*`. These entrypoints integrate with the CLI/testing harness and may load UI facades only when the UI is the real consumer.

## Import Boundaries
| Direction | Allowed | Forbidden |
|-----------|---------|-----------|
| Dev → User | ✅ Only through approved facades under `ui.services.*` (e.g. `ui.services.vision_provision`) | ❌ Direct imports of `src/ui` screens, `streamlit` components |
| User → Dev | ✅ Standard pipeline/core modules, facades (`ai.*`, `pipeline.*`, `semantic.core`) | ❌ Internal CLI modules (e.g. `timmy_kb.cli.*`) or tools that mutate local structure |

### Allowlist (module prefixes)
- `ui.services.` (interfaces into Vision, Drive, logging)
- `ui.utils.attr` (generic helpers that are UI-safe)
- `pipeline.` (path safety, logging, env, capabilities)
- `semantic.core` / `semantic.api` (SSoT semantic helpers)
- `ai.*` (assistant registry, responses, provider adapters)

### Denylist
- `ui.pages.*` imported from CLI/tools/Dev channels is forbidden.
- `timmy_kb.cli.*` and `tools.*` must never import UI components.
- `pipeline.drive.*` internal modules (client/download/upload) must not be imported directly; use `pipeline.drive_utils`.
- `src/ui` must not call `pipeline.drive.client` or `semamantic.*` private helpers directly; they should use the exposed facades.

## Examples
- User page: `ui.pages.new_client` imports `ui.services.drive_runner` but never `timmy_kb.cli` or `tools`.
- Dev CLI: `timmy_kb.cli.pre_onboarding` may import `ui.services.drive_runner` to reuse Drive tooling but never `ui.pages`.
- Tools: `tools/gen_vision_yaml.py` calls `ui.services.vision_provision.provision_from_vision_with_config` rather than running Streamlit components.

## Guardrails & References
- This contract is enforced via `tests/architecture/test_facade_imports.py` (no forbidden imports).
- Follow the Closure Protocol in `.codex/CLOSURE_AND_SKEPTIC.md` to wrap each change.
- Mentioned guardrail tests already live in `.codex/CHECKLISTS.md` and `docs/AGENTS_INDEX.md`.
- The enforcement is automated by `tools/ci/entrypoint_guard_ack.py`, which rejects changes touching public entrypoints unless `.codex/USER_DEV_SEPARATION.md` or `SEPARATION_ACK.md` is updated with rationale.
- Ownership mappings are enforced per channel via `.github/CODEOWNERS`, keeping reviews aligned with these boundaries.
- Il flusso “Nuovo cliente” ora invoca `pipeline.ownership.ensure_ownership_file()` e crea `clients/<slug>/ownership.yaml` per ogni workspace; aggiorna la governance tenant-level quando cambia la pagina `src/ui/pages/new_client.py`.

## Ownership semantics
- Ownership here describes epistemic responsibility and interface boundaries, not individual or team assignment: the **User channel** owns user-facing logic and UI safety, the **Dev channel** owns automation flows and pipeline guardrails, and the **Architecture channel** (guardrail tests + CI) owns enforcement of these boundaries.
- CODEOWNERS captures the repo-level review ownership, while tenant-level ownership lives under `clients/<slug>/ownership.yaml` (schema in `.codex/OWNERSHIP_SCHEMA.md`). Each slug file names a `superadmin` and lists the canonical `user/dev/architecture` owners for that tenant, allowing the team to trace responsibility per client.
- When modifying a surface, document which channel owns the change and ensure the other channel sees a stable interface (e.g., UI surfaces expose facades pulled by CLI/tests, Dev surfaces expose deterministic pipelines consumed by UI via `ai.*` or `pipeline.*` facades).
