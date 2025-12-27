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
  - Push behavior is coherent with the spec “push is not default” (`system/specs/promptchain_spec.md`) and with Prompt 0 `DELIVERY STRATEGY` (push only in N+1, only with explicit OCP authorization in N+1, only after QA PASS). Skeptic Gate N+1′ PASS closes the chain post N+1.
- Skeptic Gate MUST presente (Evidence/Scope/Risk/Decision e Decision=PASS) prima di avanzare al prompt successivo; PASS WITH CONDITIONS richiede vincoli, BLOCK ferma la chain (SSoT: `system/specs/promptchain_spec.md`).
- Evidence Gate reminder: se manca memo/diff/report/QA non si avanza con Prompt 1..N; il prossimo prompt rimane bloccato finché l’evidenza non ritorna completa (SSoT: `system/specs/promptchain_spec.md`).
- Skeptic Gate reminder: dopo ogni risposta operativa Codex l’OCP valuta rischi/limiti e decide se proseguire; Codex può annotare problemi ma non autorizza il passaggio.
- Codex answers must be in Italian for every Prompt Chain turn; documentation and templates remain English.

### Senior Reviewer Checklist
- For non-trivial updates (new features, security/I/O logic, integrations), run the “Dev task with Senior review” prompt in `.codex/PROMPTS.md` before inviting Codex.
- Prepare a summary message following the “Prepare the Senior review request” prompt.
- Share context, change summary, QA pipeline results, and major doubts/trade-offs with the Senior Reviewer.
- Incorporate (or discuss) the Senior Reviewer’s feedback before finishing work on protected branches.


## Security & I/O
- Validate every path via `ensure_within*`; avoid ad hoc writes.
- Write atomically and define rollback procedures for failures.
- Trial window note: mantenere lo Skeptic Gate come MUST per le prossime due Prompt Chain complete prima della retrospettiva OCP.
- Tooling/QA note: modifiche a file di tooling o configurazione devono essere autorizzate esplicitamente nel prompt che le richiede; la sola necessità di far passare la QA non basta per toccare `cspell.json`, `.pre-commit-config.yaml`, etc.


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
- Synchronize shared flags (`TIMMY_NO_GITHUB`, `GIT_DEFAULT_BRANCH`, `GIT_FORCE_ALLOWED_BRANCHES`, `TAGS_MODE`, `ui.skip_preflight`) across CLI, UI, and agents; update `.env.sample`/docs when they change.
- Confirm UI services (`ui.services.tags_adapter`, Drive runners) load; if an adapter is missing, the UI must present help/fallback (stub mode).
- Ensure structural telemetry emits consistent `phase_scope` values (prepare_repo/stage_changes/push workflows) and respects `LeaseLock`.
- Monitor throttling/cache settings (`NLP_THREADS`, `TIMMY_SAFE_PDF_CACHE_TTL`, clients_db cache); avoid divergent forks between agents and orchestrators.


## Documentation
- **[BLOCKING]** When changing signatures, flows, or UX, update `architecture.md`, `developer_guide.md`, `guida_ui.md`, or other affected docs; the PR must include an explicit `Docs:` section listing the updated files (or `n/a` if no docs change).
- Document pipeline changes in `.codex/WORKFLOWS.md` and the runbook when necessary.
