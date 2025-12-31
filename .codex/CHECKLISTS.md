# Operational Checklists

## PR / Commit
- Use conventional commit messages (feat/fix/docs/chore) describing what, why, how.
- Update minimal tests; keep the build green and linters passing.
- When touching signatures or flows, update the relevant docs (note migration steps as needed).
- Zero cSpell warnings in `docs/`.
- Respect the turn-based OCP ? Codex model defined in `system/specs/promptchain_spec.md`: process prompts in order, cite the specification as the SSoT, and never skip or reorder prompts.
- Document final QA in the closing prompt: `pytest -q` plus `pre-commit run --all-files`.
- Prompt Chain checklist: confirm Phase 0 stayed analytical/read-only with no diff/QA, each prompt 1..N produced a diff, included the Active Rules memo, executed (or justified) `pytest -q -k "not slow"`, and responded in Italian; Prompt N+1 must run `pytest -q` + `pre-commit run --all-files` and finish with an Italian one-line closing summary.
  - Prompt 0 contains **OPS AUTHORIZATION (READ-ONLY)** (whitelist + explicit forbidden actions) and **DELIVERY STRATEGY (PLANNING DECISION)** (target + push policy/gate).
  - Prompt N+1 contains commit subject (ITA) + commit id corto + commit SHA completo + SHA effettivamente pushato.
  - Push behavior is coherent with the spec “push is not default” (`system/specs/promptchain_spec.md`) and with Prompt 0 `DELIVERY STRATEGY` (push only in N+1, only with explicit OCP authorization in N+1, only after QA PASS). Skeptic Gate N+1′ PASS closes the chain post N+1 (N+1′ indicates the post‑N+1 gate, not a phase).
- Skeptic Gate MUST be present (Evidence/Scope/Risk/Decision with Decision=PASS) before advancing to the next prompt; PASS WITH CONDITIONS requires constraints, BLOCK stops the chain (SSoT: `system/specs/promptchain_spec.md`).
- Evidence Gate reminder: if memo/diff/report/QA are missing, Prompt 1..N does not advance; the next prompt remains blocked until evidence is complete (SSoT: `system/specs/promptchain_spec.md`).
- Evidence format (Prompt 1..N, N+1): report `git status --porcelain=v1`; unified diff with `diff --git` + `index` + `---/+++` + `@@`; declare `working tree dirty outside scope: YES/NO` and, if dirty, use only `git diff -- <paths in scope>` (repo‑wide diffs are forbidden when out‑of‑scope changes exist).
- Skeptic Gate reminder: after each operational Codex response the OCP evaluates risks/limits and decides whether to proceed; Codex may note issues but does not authorize progression.
- Codex answers must be in Italian for every Prompt Chain turn; documentation and templates remain English.

### Senior Reviewer Checklist
- For non-trivial updates (new features, security/I/O logic, integrations), run the “Dev task with Senior review” prompt in `.codex/PROMPTS.md` before inviting Codex.
- Prepare a summary message following the “Prepare the Senior review request” prompt.
- Share context, change summary, QA pipeline results, and major doubts/trade-offs with the Senior Reviewer.
- Incorporate (or discuss) the Senior Reviewer’s feedback before finishing work on protected branches.


## Security & I/O
- Validate every path via `ensure_within*`; avoid ad hoc writes.
- Write atomically and define rollback procedures for failures.
- Trial window note: keep the Skeptic Gate as MUST for the next two complete Prompt Chains before the OCP retrospective.
- Tooling/QA note: changes to tooling or configuration files must be explicitly authorized in the prompt that requests them; the need to pass QA alone is not sufficient to touch `cspell.json`, `.pre-commit-config.yaml`, etc.


## Pre-commit Policies
- No runtime `assert` statements in `src/` (tests only); enforced by the `forbid-runtime-asserts` hook.
- Never call `Path.write_text/bytes` in `src/`; use `safe_write_text/bytes` plus `ensure_within`. The `forbid-path-write-text-bytes` hook ensures compliance.
- Always call `ensure_within(base, target)` before writes/copies/deletes.


## UI / Workflow
- Gate the Semantica tab based on the presence of local `raw/`.
- Validate Docker preview port numbers (1–65535) and use safe container names.
- Keep `semantic/tags.db` up-to-date as the runtime SSoT.


## Drive & Git
- Ensure Drive credentials/IDs are present before running the pipeline.
- Push only `.md` files from `book/`; exclude `.md.fp` and binaries.


## Multi-agent alignment
- Synchronize shared flags (`GIT_DEFAULT_BRANCH`, `TAGS_MODE`, `ui.skip_preflight`) across CLI, UI, and agents; update `.env.sample`/docs when they change.
- Confirm UI services (`ui.services.tags_adapter`, Drive runners) load; if an adapter is missing, the UI must present help/fallback (stub mode).
- Ensure structural telemetry emits consistent `phase_scope` values (prepare_repo/stage_changes/push workflows) and respects `LeaseLock`.
- Monitor throttling/cache settings (`NLP_THREADS`, `TIMMY_SAFE_PDF_CACHE_TTL`, clients_db cache); avoid divergent forks between agents and orchestrators.


## Documentation
- **[BLOCKING]** When changing signatures, flows, or UX, update `architecture.md`, `developer_guide.md`, `guida_ui.md`, or other affected docs; the PR must include an explicit `Docs:` section listing the updated files (or `n/a` if no docs change).
- Document pipeline changes in `.codex/WORKFLOWS.md` and the runbook when necessary.
