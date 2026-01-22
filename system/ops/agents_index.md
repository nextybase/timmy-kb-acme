# AGENTS Index - Shared Policies for All Agents

Questo documento elenca gli agenti operativi del sistema,
che operano esclusivamente nel dominio dell'**Agency Engine**.

Gli agenti non accedono direttamente ai dati grezzi
né ai processi di ingestione:
operano sempre entro i confini fissati
dall'**Epistemic Envelope**.

This index gathers the shared policies that every agent must follow in the repository. Avoid duplicating rules: the individual `AGENTS.md` files under their respective areas should contain only the minimal, scope-specific overrides and point back to this index for everything else.


## Operational Approach (Agent-first, HiTL)

The repository treats the agent as a teammate with clear responsibilities: the **common policies** live here, and area-specific `AGENTS.md` files define only **local overrides**. The workflow is **Human-in-the-Loop**: the agent proposes idempotent micro-PRs, avoids side effects, and closes the loop with lint/type/test.

L'agency è sempre mediata, contestuale e revocabile.
Nessun agente può produrre conoscenza
al di fuori dell'Epistemic Envelope attivo.

Core principles:
- **SSoT & Safety:** all reads/writes go through the utility belt and stay within the workspace; no unannounced collateral effects.
- **Micro-PR:** small, motivated changes with a clear diff; touching area X requires syncing docs/tests and related buffers.
- **Matrix as contract:** the table below is the single source of truth across domains: build/test/lint/path-safety/documentation are obligations, not suggestions.
- **Gating UX:** UI surfaces obey state (e.g., Semantica unlocks only when RAW exists) to avoid non-idempotent operations.
## Agency-first model & control plane
- WHAT (governance): ProtoTimmy/Timmy represent the agency that makes decisions, coordinates Domain Gatekeepers (validation), and relies on the Control Plane / Engineering Gatekeeper (OCP) to apply HiTL gates; the Prompt Chain lifecycle and Intent/Action registry live in `instructions/*`.
- HOW (execution): `pipeline.*` helpers, CLI flows, semantic services, and Codex/micro-agent workflows execute the foundation pipeline (markdown enrichment + knowledge graph validation) under Work Order Envelope (OK / NEED_INPUT / CONTRACT_ERROR) without decision-making authority.
- Timmy assumes agency only once the foundation pipeline produces the required artifacts; until then ProtoTimmy and the control plane keep the execution aligned to the SSoT and hand off to Timmy after validation.

<!-- MATRIX:BEGIN -->
> **Override matrix (quick overview)**
> Local `AGENTS.md` files define only overrides; the common policies remain in this index.

| Area | File | Key overrides (summary) | Acceptance criteria (key) | Notes | Typical agent tasks |
|------|------|---------------------------|-------------------------------|------|-------------------------|
| Root | `AGENTS.md` | Read `system/ops/runbook_codex.md` and the `.codex/` guides before starting any task to align on workflows and standards. | No activity starts until the runbook and supporting `.codex/` documents have been reviewed. |  | Runbook/.codex alignment<br>Verify mandatory documents |
| Pipeline Core | `src/pipeline/AGENTS.md` | Path safety is mandatory: all writes/copies/deletes must travel through `ensure_within*` instead of manual joins.; Enforce atomic writes via `safe_write_text`/`safe_write_bytes`. | No write or delete happens outside the customer workspace. |  | Pipeline path-safety hardening<br>I/O refactor to SSoT utilities<br>Structured pipeline/run logging |
| Semantica | `src/semantic/AGENTS.md` | Use the public `semantic.api` facade; avoid imports or invocations of `_private` helpers.; Treat `semantic/tags.db` as the runtime SSoT; reserve `tags_reviewed.yaml` for manual authoring or migration checkpoints. | Enrichment must not duplicate tags, must honor synonyms/aliases, and must leave non-frontmatter content untouched. |  | Align `semantic.api` vs services<br>Regenerate/migrate `tags.db`<br>Idempotent README/SUMMARY fallback |
| UI (Streamlit) | `src/ui/AGENTS.md` | Follow `docs/streamlit_ui.md` for routing, state management, I/O, and logging; the flow should cover configuration → Drive (provisioning + README + RAW download) → Semantics (convert/enrich → README/SUMMARY → Preview).; Gate the Semantica tab so it is enabled only when `raw/` is present locally. | Never trigger Semantica actions if `raw/` is empty or missing. | State-driven UX | Refactor UI onboarding orchestrators<br>Audit RAW/slug gating and `st.navigation` router<br>Consistent `ui.<page>` messaging/logging |
| UI (Streamlit Pages) | `src/ui/pages/AGENTS.md` | Require Streamlit 1.50.0+ with native routing (`st.Page` + `st.navigation`); custom routers are disallowed.; Keep imports safe: no I/O or side effects during import; centralize `st.set_page_config` within the entrypoint. | Native routing (`st.Page`/`st.navigation`) is present with internal links handled by `st.page_link`; queries/slugs rely solely on dedicated helpers. | State-driven UX | Sweep Streamlit 1.50 deprecations<br>Native `st.Page`/`st.navigation` router compliance<br>Path-safety and page logging |
| UI Fine Tuning | `src/ui/fine_tuning/AGENTS.md` | Force read-only assistant details (id, model, system prompt) with copy/export actions; dry-run outputs are raw and the review of configurable fields requires explicit confirmation before remote writes.; Expose proposed assistant changes as HiTL micro-PRs with clear motivation and annotated diffs. | The System Prompt modal displays `assistant_id`, `model`, full instructions, and a copy button; dry-run output remains unaltered. |  | Assistant modal read-only + export<br>Dry-run with raw output<br>Micro-PR proposals for assistant config |
| Test | `tests/AGENTS.md` | Generate dummy data with dedicated tools; never use real datasets.; Avoid network dependencies: mock or bypass Drive/Git interactions. | Local builds/tests pass with smoke E2E executed on reproducible dummy slugs. |  | Mock Drive/Git and dummy fixtures<br>Contract test for `book/` guard<br>Smoke E2E with sample slug |
| Documentazione | `docs/AGENTS.md` | Not defined | Not defined |  | cSpell and frontmatter sweep<br>Align README/docs on new features<br>Update guides with current orchestrators |
| Codex (repo) | `.codex/AGENTS.md` | Path-safety: write only within `src/`, `tests/`, `docs/`, `.codex/`; never touch `config/**`, `.env*`, `output/**`; conversations in Italian by default when referencing this perimeter.; Atomic I/O via SSoT helpers (`ensure_within*`, `safe_write_*`), no import-time side effects. | Path safety enforced (writes limited to `src/`, `tests/`, `docs/`, `.codex/` without exception). |  | Standard QA pipeline execution<br>Align use of GitHub helpers<br>Reuse shared vision/UI tools |

<!-- MATRIX:END -->


## Common Policies
- **Build:** keep scripts idempotent; avoid global side effects or undeclared state changes.
- **Test:** run tests locally deterministically; no network dependencies in unit tests. Use markers/filters as needed (e.g., `-m drive`, `-m slow`).
- **Lint & Typecheck:** apply configured formatters/linters (`Ruff`, `Black`, `isort`) and typecheckers (`mypy`/`pyright`) when present. Respect the project's existing standards.
- **Path-safety & I/O:** every read/write must flow through the SSoT helpers (`ensure_within*`, `safe_write_*`). Never create/delete files outside the customer perimeter.
- **Documentation & QA:** update documentation when UX/flow changes occur. Keep cSpell clean on tracked paths; only expand dictionaries for domain-specific terms.
 - **Prompt Chain etiquette:** Planner → OCP → Codex → OCP → Planner is mandatory; Phase 0 stays analytical, phases 1..N implement micro-PRs with `pytest -q -k "not slow"`, and Prompt N+1 executes `pytest -q` + `pre-commit run --all-files`, ending with an Italian one-line closing commit. SSoT documentation remains in English, while Codex always responds in Italian. Reference: `system/specs/promptchain_spec.md`, `system/ops/runbook_codex.md`, `.codex/PROMPTS.md`.


## Anti-duplication note
- Common sections belong in this index.
- Local `AGENTS.md` files should only describe area-specific overrides and link explicitly back to this index.
