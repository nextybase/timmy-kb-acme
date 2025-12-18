# Runbook Codex – Timmy KB (v1.0 Beta)

> This runbook is the operational guide for working safely and effectively on the Timmy KB repository with an agent-first, HiTL approach. It serves as the day-to-day reference for flows; design details live in the supporting documents cited below.

- **Audience:** developers, tech writers, QA, maintainers, and the repo-aware agent Codex.
- **Scope:** local operations, UI/CLI flows, OpenAI/Drive/GitHub integrations, secure I/O and path safety, rollback, and incident response.
- **Canonical references:** [Developer Guide](developer_guide.md), [Coding Rules](coding_rule.md), [Architecture Overview](architecture.md), [AGENTS Index](AGENTS_INDEX.md), [.codex/WORKFLOWS](../.codex/WORKFLOWS.md), [.codex/CHECKLISTS](../.codex/CHECKLISTS.md), [User Guide](user_guide.md).

## Visual summary of the Codex system

This repository blends the shared policies (`docs/AGENTS_INDEX.md`), area overrides (`AGENTS.md`), prompt APIs (`.codex/PROMPTS.md`), the runbook, and workflow documentation. Codex follows the integration guidelines (`docs/guida_codex.md`) and uses the Onboarding Task as the entry point. The flow is: AGENTS → Onboarding prompt → micro-PR + QA → matrix updates.

> Note: `docs/guida_codex.md` describes the mental model for the Codex + Repo-aware workflow (v2) and mandates the three SSoT documents (AGENTS index, area AGENTS, `~/.codex/AGENTS.md`). The runbook remains the practical flow guide.

---

## 1) Prerequisites & quick setup

### Minimal tooling
- Python **>= 3.11**, pip, pip-tools; optional Docker for HonKit preview.
- Required credentials: `OPENAI_API_KEY`, `GITHUB_TOKEN`. Drive access also needs `SERVICE_ACCOUNT_FILE` and `DRIVE_ID`. <!-- pragma: allowlist secret -->
- Install pre-commit hooks: `pre-commit install --hook-type pre-commit --hook-type pre-push`.
- Ensure the pipeline modules import from the same repo root as the UI; activate the correct venv and run `pip install -e .` at the repo root if necessary.

### Environment setup
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt   # for Drive integration
make qa-safe
pytest -q
```

References: [README](../README.md), [Developer Guide → Dependencies & QA](developer_guide.md).

### Codex operational alignment
- Before any work, the Codex agent loads the three SSoT documents (`docs/AGENTS_INDEX.md`, the relevant `AGENTS.md`, and `~/.codex/AGENTS.md`) and uses `.codex/PROMPTS.md` as the API.
- The recommended entry point is the Onboarding Task Codex; it inflicts a plan-first, micro-PR, QA-compliant workflow and insists on updating the documentation and AGENTS matrix when touched.
- Codex flows must remain consistent with the policies in this runbook and the AGENTS matrix.

### Codex integration
- `.codex/PROMPTS.md` defines the operational API for Codex.
- Before each agent-based job, run the startup block: read `docs/AGENTS_INDEX.md`, the relevant area `AGENTS.md`, `.codex/AGENTS.md`, and this runbook.
- The Onboarding Task Codex prompt enforces planning, micro-PR behavior, QA guardrails (path safety, atomic writes, structured logging), and AGENTS matrix maintenance.

### Prompt Chain governance
- The Prompt Chain follows the turn-based protocol in `docs/PromptChain_spec.md`: Planner → OCP → Codex → OCP → Planner with exactly one action per prompt.
- Phase 0 prompts (Prompt 0, 0a..0x) are analytical/read-only and must confirm the SSoT documents before any diff is produced.
- Phase 1..N prompts are operational micro-PRs that touch files declared by the OCP, include the Active Rules memo, and run at least `pytest -q -k "not slow"` before proceeding.
- Prompt N+1 runs the final QA (`pre-commit run --all-files` + `pytest -q`), documents retries (up to ten), and ends with an Italian one-line closing commit summary.
- Codex responses must be in Italian on every prompt; documentation and templates remain in English to preserve the SSoT.
- The OCP issues one prompt at a time, Codex replies with a diff/report and waits, and no prompt may skip a phase or bypass the final QA.
- Every prompt must preserve the canonical header defined in `.codex/PROMPTS.md`, starting with `ROLE: Codex` and continuing with `PHASE`, `SCOPE`, `ACTIVE RULES MEMO`, `EXPECTED OUTPUTS`, `TESTS`, `CONSTRAINTS`, and `STOP RULE`. Codex and OCP rely on this structure to detect malformed prompts: absence or misassignment of the `ROLE` line halts the chain until corrected.
- L’OCP ha inoltre la prerogativa esclusiva di approvare i prompt OPS/RUN (Phase 1..N e Prompt N+1) prima di inoltrarli a Codex: la decisione umana deve essere già registrata quando il prompt arriva nell’Active Rules memo. Codex non deve richiedere conferme, né gestire questo gate; esegue la micro-PR solo dopo aver ricevuto il prompt autorizzato e mantiene reporting completo (memo + diff/report/QA) per il gate successivo.

---

## 2) Configuration: secrets vs versioned config

- **SSoT:** keep secrets outside the repo (`.env`), and versioned configuration inside `config/config.yaml`. Reference: [docs/configurazione.md](configurazione.md).
- Example snippet (for reference: `config/config.yaml`, see also `config/config.example.yaml`):
```yaml
meta:
  client_name: "Cliente Demo"
ui:
  skip_preflight: true
  allow_local_only: true
  admin_local_mode: false
ai:
  openai:
    timeout: 120
    max_retries: 2
    http2_enabled: false
  vision:
    model: gpt-4o-mini-2024-07-18
    engine: assistants
    assistant_id_env: OBNEXT_ASSISTANT_ID
    snapshot_retention_days: 30
pipeline:
  retriever:
    auto_by_budget: false
    throttle:
      candidate_limit: 3000
      latency_budget_ms: 300
      parallelism: 1
      sleep_ms_between_calls: 0
  raw_cache:
    ttl_seconds: 300
    max_entries: 8
```

- Operational rules:
  - CLI/UI consumers read `ai.vision.model`.
  - The Assistant flow uses `ai.vision.assistant_id_env` for the ENV override.
  - UI obtains the model via `get_vision_model()` (SSoT).
  - Retriever adheres to throttle limits and logs `retriever.query.embed_failed`, short-circuiting to an empty result when budgets are exhausted.
  - Flags such as `ui.allow_local_only` and `ui.admin_local_mode` gate Admin access.

References: [Developer Guide → Configuration](developer_guide.md), [Configuration Overview](configurazione.md).

---

## 3) Security & path safety (mandatory)

- **Path safety:** route all I/O through `pipeline.path_utils.ensure_within*`.
- **Atomic writes:** use `pipeline.file_utils.safe_write_text/bytes` with temporary files and replacements.
- **Structured logging:** use `pipeline.logging_utils.get_structured_logger`, enabling redaction when `LOG_REDACTION` is active.
  - Log rotation is adjustable via `TIMMY_LOG_MAX_BYTES` and `TIMMY_LOG_BACKUP_COUNT`.
  - Customer logs live in `output/timmy-kb-<slug>/logs/`; global UI logs are in `.timmykb/logs/`.
  - The UI entrypoint writes `.timmykb/logs/ui.log` with shared handlers; Promtail augments logs with `run_id`, `trace_id`, and `span_id`.
  - `TIMMY_LOG_PROPAGATE` forces handler propagation; avoid console duplication by not overriding it unless required.
  - OTLP tracing uses `TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, and `TIMMY_ENV`.
- **Hashing & masking:** use `hash_identifier`/`sha256_path` with `TIMMY_HASH_SALT`, and prefer `mask_id_map` for sensitive extras.
- **RAW PDF cache:** `iter_safe_pdfs` uses an LRU cache controlled by config TTL and size; safe writes invalidate and preload caches.
- **Frontmatter caching:** post-write cache alignment with a 256-entry LRU; `semantic.api` clears caches after runs to avoid stale reuse.
- **UI import safety:** avoid import-time side effects; wrappers must keep signature parity with the backend.
- **Drive downloads:** UI downloads only missing PDFs. To overwrite, toggle "Overwrite conflicting local files" or manually rename files.
- **Preview stubs:** `PREVIEW_LOG_DIR` may point to absolute paths; if unreachable, fallback to `logs/preview` and notify the user.
- **Ingest telemetry:** events such as `ingest.embed`, `ingest.persist`, `ingest.process_file`, `ingest.summary` must include `artifact_count`. Use these for dashboards and alerts.
- **Streaming ingest:** `ingest_folder` runs streaming globs with throttling controls (`max_files`, `batch_size`) to prevent OOM in migrations.

### Observability stack
- Config lives in `observability/docker-compose.yaml` and `observability/promtail-config.yaml`.
- Promtail monitors `../output/` and `../.timmykb/logs/`, tagging logs with `slug`, `run_id`, and `event`.
- Start locally with `docker compose up -d` inside `observability/`; Grafana listens on port 3000, Loki on 3100. Remember to map `output` and `.timmykb` in Docker Desktop on Windows.
- Newer stack includes `tempo` (ports 3200/4317) and `otel-collector` (port 4318) for OTLP tracing.
- The UI log dashboard or `tools/observability_stack.py` can pulse the stack with the same env/compose files.

---

## 4) Operational flows (UI/CLI)

> Objective: turn PDFs into KB Markdown with coherent frontmatter, README/SUMMARY updates, a HonKit Docker preview, and an optional GitHub push.

### Standard workflow
1. **pre_onboarding:** create the workspace (`output/timmy-kb-<slug>/...`), optionally provision Drive, and upload `config.yaml`.
2. **tag_onboarding:** produce `semantic/tags_raw.csv` and the HiTL checkpoint `tags_reviewed.yaml`.
3. **semantic_onboarding (via `semantic.api`):** convert PDFs to Markdown in `book/`, enrich frontmatter using `semantic/tags.db`, and rebuild README/SUMMARY with Docker preview orchestration.
4. **onboarding_full:** run Markdown preflight on `book/` and perform the GitHub push.

### UI gating
- Enable the Semantica tab only once local RAW data exists.
- Docker preview needs safe port validation and container naming.
- Telemetry event `semantic.book.frontmatter` tracks enriched file counts.

References: [.codex/WORKFLOWS.md](../.codex/WORKFLOWS.md), [User Guide](user_guide.md), [Architecture](architecture.md).

---

## 5) Codex scenarios (repo-aware)

### 5.0 Common operating principles (v2)
- The default scenario is Agent mode with path safety, atomic writes, and doc/test updates.
- All activities follow Codex v2 (see `docs/guida_codex.md`), the AGENTS perimeter, and explicit micro-PR + QA.
- Select prompts from `.codex/PROMPTS.md`; the Onboarding Task Codex is mandatory.
- Collaboration between developer, Codex, and Senior Reviewer guides sensitive tasks.

### 5.1 Chat scenario
- Reasoning/drafting only; no I/O. Useful for grooming, drafts, or quick checks.

### 5.2 Agent scenario (recommended)
- Codex works on-rails: path safety, atomic writes, micro-PRs, docs/tests updated in the same change set.
- The policy matrix (`AGENTS Index`) defines scope limits.

### 5.3 Full Access scenario (exceptional)
- Restricted to dedicated branches for explicit tasks (scale migrations).
- Use internal GitHub helpers: `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`, along with `pipeline.github_env_flags`.
- Delegated semantic pipeline steps call `semantic.convert_service`, `semantic.frontmatter_service`, and `semantic.embedding_service`; the `semantic.api` facade re-exports public helpers.
- NLP stages such as doc_terms/cluster go through `semantic.nlp_runner.run_doc_terms_pipeline` and `tag_onboarding.run_nlp_to_db`.
- Log every step; keep PRs/commits atomic and traceable.

### 5.4 Multi-agent alignment
- Sync shared flags (`TIMMY_NO_GITHUB`, `GIT_FORCE_ALLOWED_BRANCHES`, `TAGS_MODE`, throttles) across UI, CLI, and agents; update `.env.sample` and docs when they change.
- Ensure adapters (`ui.services.tags_adapter`, Drive services) load or that the UI shows stub help/fallback.
- Emit `phase_scope` telemetry for `prepare_repo`, `stage_changes`, and push phases.
- Reset shared caches (`clients_store`, `safe_pdf_cache`) after atomic writes and log `reset_gating_cache`.

### 5.5 Prompt Chain execution
- Flow: User (Timmy/ProtoTimmy) → OrchestratoreChainPrompt (OCP) generates numbered prompts → OCP sends each prompt to Codex, who executes it as a micro-PR.
- Always start with the Onboarding Task Codex and respect the provided scope.
- Each step adheres to AGENT-first, HiTL, path safety, QA, and atomic writes. The OCP never edits the repo.
- Track every step in summaries/logs so the chain remains reproducible and idempotent.
- For governance details, refer to `docs/PromptChain_spec.md`.

References: [AGENTS Index](AGENTS_INDEX.md), [.codex/AGENTS.md](../.codex/AGENTS.md).

---

## 6) Quality, testing & CI

- Test pyramid: units → contract/middle → smoke E2E (dummy datasets, no network).
- Pre-commit hooks run formatters/linters (`isort`, `black`, `ruff --fix`), typechecks (`mypy`/`pyright`), spell-check (`cspell`), and guard rails (`forbid-*`).
- Rapid local CI: `make qa-safe` → `make ci-safe` → `pytest -q`.

### Required checks
- Reject invalid slugs or normalize them.
- Deny traversal via symlinks in `raw/`.
- Maintain UI/backend wrapper parity and parameter pass-through.
- Keep `book/` invariants: `README.md`/`SUMMARY.md` must exist; `.md.fp` files stay out of pushes.

References: [Developer Guide → Test](developer_guide.md), [Coding Rules → Test & Quality](coding_rule.md), [.codex/CHECKLISTS](../.codex/CHECKLISTS.md).

---

## 7) Telemetry & operational security

- Centralize logs in `output/timmy-kb-<slug>/logs/` using key=value format.
- Automatically redact secrets by setting `LOG_REDACTION=1`.
- Use health-check scripts and hooks (`fix-control-chars`, `forbid-control-chars`) to manage characters/encoding.
- Throttle retriever queries: emit a warning (`retriever.throttle.deadline`) when budgets are depleted and clamp `candidate_limit`.

References: [README → Telemetry & Security](../README.md), [User Guide → Character Checks](user_guide.md).

---

## 8) Debug explainability (lineage)

- For suspicious embeddings/chunks, log `slug/scope/path` and use events such as `semantic.input.received`, `semantic.lineage.chunk_created`, and `semantic.lineage.embedding_registered`.
- In Chat/Agent mode, query the DB or logs for `meta["lineage"]` without changing the schema; propose fixes only if they remain idempotent.
- Align explainability events with `docs/logging_events.md` and update `meta["lineage"]` if chunk/embedding creation changes.

### Explainability audits
- Store a per-response manifest (`response_id.json`) path-safely and atomically.
- Retriever emits `retriever.response.manifest` without exposing text snippets.
- Use `ExplainabilityService` to enrich lineage/logs for auditing.

---

## 9) GitHub operations & rollback

### Publishing CLI
```bash
py src/onboarding_full.py --slug <slug>
```
Push only `.md` files from `book/` to the destination branch.

### Orchestration rules
- Always use the Git helpers `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease`.
- Stub `_prepare_repo`/`_stage_changes` in tests per `tests/pipeline/test_github_push.py`.
- Configure GitHub locks via env flags (`TIMMY_GITHUB_LOCK_TIMEOUT_S`, etc.).

### Rollback guidance
- On push failures, `_push_with_retry` retries with backoff while leaving the local state repeatable.
- For diverging branches, use `_force_push_with_lease` with explanations.
- Revert invalid content atomically and rerun preflight (Markdown only, no `.md.fp`).

References: [.codex/AGENTS](../.codex/AGENTS.md).

---

## 10) Governance & AGENTS matrix

- The AGENTS Index (`AGENTS_INDEX.md`) is the SSoT.
- Local `AGENTS.md` files define overrides and link back to the index.
- Keep the matrix aligned using `pre-commit run agents-matrix-check --all-files` whenever AGENTS files change.
- CI runs `python tools/gen_agents_matrix.py --check` and fails if the matrix is outdated.

References highlighted area AGENTS as needed.

---

## 11) UI/refactor patterns

- Apply the Collector + Orchestrator pattern to separate checks from coordination while respecting output order.
- Refactors must remain non-breaking, maintain signatures and message semantics, and avoid import-time side effects.
- Logging should be minimal, structured (`run_start`, `check_failed`, `run_complete`), and free of sensitive data.

---

## 12) Streamlit operations

- Enforce native routing (`st.Page` + `st.navigation`) with `ui.utils.route_state`/`ui.utils.slug`.
- Gate Semantica on `raw/` presence and keep messages short while logging details.
- Perform all I/O via SSoT utilities; avoid manual writes.

References: [src/ui/AGENTS.md](../src/ui/AGENTS.md), [src/ui/pages/AGENTS.md](../src/ui/pages/AGENTS.md), [User Guide → UI](user_guide.md).

---

## 13) Vision statement & AI tooling

- `src/tools/gen_vision_yaml.py` generates `semantic/semantic_mapping.yaml` from `config/VisionStatement.pdf`.
- UI always reads the model from `config/config.yaml` via `get_vision_model()` (SSoT).
- Prefer the Agent scenario; allow Full Access only with explicit justification and on a dedicated branch.
- `tools/vision_alignment_check.py` exports assistant metadata for diagnostics and logs.
- `use_kb` follows SSoT settings with optional overrides (`VISION_USE_KB`) for File Search gating.

References: [User Guide → Vision Statement](user_guide.md), [Developer Guide → Configuration](developer_guide.md).

---

## 14) Operational checklists (excerpt)

- PR/Commit: conventional messages, updated tests, zero cSpell warnings.
- Security & I/O: path-safe ensures, atomic writes, defined rollback paths.
- UI/Workflow: gate Semantica, secure Docker preview, maintain `semantic/tags.db`.
- Drive/Git: credentials ready, push only `.md` from `book/`.
- Documentation (blocking): update Architecture/Developer Guide/User Guide (and `.codex/WORKFLOWS.md` when pipeline changes) and list the updates in the PR's `Docs:` section.

References: [.codex/CHECKLISTS](../.codex/CHECKLISTS.md).

---

## 15) Troubleshooting

- **Drive doesn’t download PDFs:** regenerate the README in `raw/`, verify permissions and `DRIVE_ID`.
- **HonKit preview doesn’t start:** check Docker and the port availability.
- **Conversion failures:** ensure valid PDFs exist within the allowed perimeter (avoid symlinks).
- **Spell-check/docs mismatch:** run cSpell on the docs and align frontmatter/title versions.
- **Model inconsistency:** check `config/config.yaml` and `get_vision_model()`.

References: [User Guide → Troubleshooting](user_guide.md).

---

## 16) ADR & design changes

- Log architectural decisions as ADRs inside `docs/adr/`.
- Update the ADR index and link new documents; mark superseded entries accordingly.

References: [docs/adr/README.md](adr/README.md).

---

## 17) Synthetic policies

1. **SSoT & Safety:** enforce utility-based I/O; never write outside the workspace.
2. **Micro-PR:** keep diffs small and grounded; update dependent docs/tests when touching an area.
3. **UI import-safe:** avoid import-time side effects.
4. **Gating UX:** state-driven actions (Semantica only with RAW).
5. **Docs & Versioning:** keep README/docs/frontmatter aligned with `v1.0 Beta`.
6. **AGENTS matrix:** always current; run `agents-matrix-check` when editing AGENTS files.

---

## 18) Useful commands
```bash
# UI
streamlit run onboarding_ui.py

# CLI orchestrators
py src/pre_onboarding.py --slug <slug> --name "<Cliente>" --non-interactive
py src/tag_onboarding.py --slug <slug> --non-interactive --proceed
py src/tag_onboarding.py --slug <slug> --nlp --nlp-workers 6 --nlp-batch-size 8
py src/semantic_onboarding.py --slug <slug> --non-interactive
py src/onboarding_full.py --slug <slug> --non-interactive

# QA
make qa-safe
pytest -q
pre-commit run --all-files

# Spell & encoding
pre-commit run cspell --all-files
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files
```
