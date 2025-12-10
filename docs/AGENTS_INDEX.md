# AGENTS Index – Shared Policies for All Agents

This index gathers the shared policies that every agent must follow in the repository. Avoid duplicating rules: the individual `AGENTS.md` files under their respective areas should contain only the minimal, scope-specific overrides and point back to this index for everything else.


## Operational Approach (Agent-first, HiTL)

The repository treats the agent as a teammate with clear responsibilities: the **common policies** live here, and area-specific `AGENTS.md` files define only **local overrides**. The workflow is **Human-in-the-Loop**: the agent proposes idempotent micro-PRs, avoids side effects, and closes the loop with lint/type/test.

Core principles:
- **SSoT & Safety:** all reads/writes go through the utility belt and stay within the workspace; no unannounced collateral effects.
- **Micro-PR:** small, motivated changes with a clear diff; touching area X requires syncing docs/tests and related buffers.
- **Matrix as contract:** the table below is the single source of truth across domains: build/test/lint/path-safety/documentation are obligations, not suggestions.
- **Gating UX:** UI surfaces obey state (e.g., Semantica unlocks only when RAW exists) to avoid non-idempotent operations.


<!-- MATRIX:BEGIN -->
> **Matrice di override (panoramica rapida)**
> Gli `AGENTS.md` locali definiscono solo le deroghe/override; le policy comuni restano in questo indice.

| Area | File | Override chiave (sintesi) | Criteri di accettazione (key) | Note | Task tipici dell'agente |
|------|------|---------------------------|-------------------------------|------|-------------------------|
| Root | `AGENTS.md` | ???'???? | No activity starts until the runbook and supporting `.codex/` documents have been reviewed. |  | Allineamento runbook `.codex/`<br>Verifica documenti obbligatori |
| Pipeline Core | `src/pipeline/AGENTS.md` | ???'???? | No write or delete happens outside the customer workspace. |  | Hardening path-safety pipeline<br>Refactor I/O su utility SSoT<br>Log strutturato pipeline/run |
| Semantica | `src/semantic/AGENTS.md` | ???'???? | Enrichment must not duplicate tags, must honor synonyms/aliases, and must leave non-frontmatter content untouched. |  | Allineamento `semantic.api` vs service<br>Rigenerazione/migrazione `tags.db`<br>Fallback README/SUMMARY idempotenti |
| UI (Streamlit) | `src/ui/AGENTS.md` | ???'???? | Never trigger Semantica actions if `raw/` is empty or missing. | UX guidata da stato | Refactor orchestratori UI onboarding<br>Audit gating RAW/slug e router `st.navigation`<br>Messaggistica/log `ui.<pagina>` coerente |
| UI (Streamlit) | `src/ui/pages/AGENTS.md` | ???'???? | Native routing (`st.Page`/`st.navigation`) is present with internal links handled by `st.page_link`; queries/slugs rely solely on dedicated helpers. | UX guidata da stato | Sweep deprecazioni Streamlit 1.50<br>Router nativo `st.Page`/`st.navigation` compliance<br>Path-safety e logging per pagine |
| UI Fine Tuning | `src/ui/fine_tuning/AGENTS.md` | ???'???? | The System Prompt modal displays `assistant_id`, `model`, full instructions, and a copy button; dry-run output remains unaltered. |  | Modal Assistant read-only + export<br>Dry-run con output grezzo<br>Proposte micro-PR per config Assistant |
| Test | `tests/AGENTS.md` | ???'???? | Local builds/tests pass with smoke E2E executed on reproducible dummy slugs. |  | Mock Drive/Git e fixture dummy<br>Contract test su guard `book/`<br>Smoke E2E slug di esempio |
| Documentazione | `docs/AGENTS.md` | ???'???? | Clean spell-check results on `docs/` and `README.md` without ad-hoc ignores. |  | Sweep cSpell e frontmatter versione<br>Allineamento README/docs su nuove feature<br>Aggiornare guide con orchestratori correnti |
| Codex (repo) | `.codex/AGENTS.md` | ???'???? | Path safety enforced (writes limited to `src/`, `tests/`, `docs/`, `.codex/` without exception). |  | Esecuzione pipeline QA standard<br>Allineamento uso helper GitHub<br>Riuso tool vision/UI condivisi |

<!-- MATRIX:END -->


## Common Policies
- **Build:** keep scripts idempotent; avoid global side effects or undeclared state changes.
- **Test:** run tests locally deterministically; no network dependencies in unit tests. Use markers/filters as needed (e.g., `-m drive`, `-m push`, `-m slow`).
- **Lint & Typecheck:** apply configured formatters/linters (`Ruff`, `Black`, `isort`) and typecheckers (`mypy`/`pyright`) when present. Respect the project's existing standards.
- **Path-safety & I/O:** every read/write must flow through the SSoT helpers (`ensure_within*`, `safe_write_*`). Never create/delete files outside the customer perimeter.
- **Documentation & QA:** update documentation when UX/flow changes occur. Keep cSpell clean on tracked paths; only expand dictionaries for domain-specific terms.
 - **Prompt Chain etiquette:** Planner → OCP → Codex → OCP → Planner is mandatory; Phase 0 stays analytical, phases 1..N implement micro-PRs with `pytest -q -k "not slow"`, and Prompt N+1 executes `pytest -q` + `pre-commit run --all-files`, ending with an Italian one-line closing commit. Documentazione SSoT resta in inglese, ma Codex risponde sempre in italiano. Reference: `docs/PromptChain_spec.md`, `docs/runbook_codex.md`, `.codex/PROMPTS.md`.


## Local AGENTS references
- Pipeline Core: `src/pipeline/AGENTS.md`
- Semantics: `src/semantic/AGENTS.md`
- UI: `src/ui/AGENTS.md`
- UI (Pages): `src/ui/pages/AGENTS.md`
- Test: `tests/AGENTS.md`
- Documentation: `docs/AGENTS.md`
- Repository root: `AGENTS.md`
- Codex (repo): `.codex/AGENTS.md`


## Anti-duplication note
- Common sections belong in this index.
- Local `AGENTS.md` files should only describe area-specific overrides and link explicitly back to this index.
