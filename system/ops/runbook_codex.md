# Runbook Codex - Timmy KB (v1.0 Beta)

Questo runbook descrive il flusso operativo tra OCP e Codex
all'interno dell'**Agency Engine**.

L'Agency Engine è il dominio deliberativo del sistema
e opera sempre entro i vincoli definiti
dall'**Epistemic Envelope**.

---

> This runbook is the operational guide for working safely and effectively on the Timmy KB repository with an agent-first, HiTL approach. It serves as the day-to-day reference for flows; design details live in the supporting documents cited below.

- **Audience:** developers, tech writers, QA, maintainers, and the repo-aware agent Codex.
- **Scope:** local operations, UI/CLI flows, OpenAI/Drive integrations, secure I/O and path safety, rollback, and incident response.
- **Canonical references:** [Developer Guide](../../docs/developer/developer_guide.md), [Coding Rules](../../docs/developer/coding_rule.md), [Architecture Overview](../architecture.md), [AGENTS Index](agents_index.md), [Environment Certification Policy](../../docs/policies/environment_certification.md), [.codex/WORKFLOWS](../../.codex/WORKFLOWS.md), [.codex/CHECKLISTS](../../.codex/CHECKLISTS.md), [User Guide](../../docs/user/user_guide.md), [.codex/USER_DEV_SEPARATION](../../.codex/USER_DEV_SEPARATION.md).

## Visual summary of the Codex system

This repository blends the shared policies (`system/ops/agents_index.md`), area overrides (`AGENTS.md`), prompt APIs (`.codex/PROMPTS.md`), the runbook, and workflow documentation. Codex follows the integration manual (`docs/guida_codex.md`) and uses the Onboarding Task as the entry point. The flow is: AGENTS → Onboarding prompt → micro-PR + QA → matrix updates.

> Note: the Prompt Chain governance SSoT is `system/specs/promptchain_spec.md`. The Codex integration manual lives in `docs/guida_codex.md` and references the three SSoT documents (AGENTS index, area AGENTS, `~/.codex/AGENTS.md`). The runbook remains the practical flow guide.

---

## 1) Prerequisites & quick setup

### Minimal tooling
- Python **>= 3.11**, pip, pip-tools; optional Docker for HonKit preview.
- Required credentials: `OPENAI_API_KEY`. Drive access also needs `SERVICE_ACCOUNT_FILE` and `DRIVE_ID`. <!-- pragma: allowlist secret -->
- Install pre-commit hooks: `pre-commit install --hook-type pre-commit`.
- Ensure the pipeline modules import from the same repo root as the UI; activate the correct venv and run `pip install -e .` at the repo root if necessary.

### Environment setup
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt   # for Drive integration
make qa-safe
pytest -q
```

References: [README](../README.md), [Developer Guide → Dependencies & QA](../../docs/developer/developer_guide.md).

### Codex operational alignment
- Before any work, the Codex agent loads the three SSoT documents (`system/ops/agents_index.md`, the relevant `AGENTS.md`, and `~/.codex/AGENTS.md`) and uses `.codex/PROMPTS.md` as the API.
- The recommended entry point is the Onboarding Task Codex; it inflicts a plan-first, micro-PR, QA-compliant workflow and insists on updating the documentation and AGENTS matrix when touched.
- Codex flows must remain consistent with the policies in this runbook and the AGENTS matrix.
- Poiché il workstream finisce solo con un Prompt Closure, ogni Prompt Chain viene chiusa solo dopo il **Closure Protocol** (`.codex/CLOSURE_AND_SKEPTIC.md`), che lega Prompt N+1 (Codex) e lo Skeptic Gate post N+1 (OCP), talvolta indicato come "N+1′" senza essere una fase distinta.
- Per la separazione Netta tra canale User e Dev, consultare `.codex/USER_DEV_SEPARATION.md` e rispettare i guardrail `tests/architecture/test_facade_imports.py` e `tests/architecture/test_dev_does_not_import_ui.py` prima di chiudere la catena.

### Codex integration
- `.codex/PROMPTS.md` defines the operational API for Codex.
- Before each agent-based job, run the startup block: read `system/ops/agents_index.md`, the relevant area `AGENTS.md`, `.codex/AGENTS.md`, and this runbook.
- The Onboarding Task Codex prompt enforces planning, micro-PR behavior, QA guardrails (path safety, atomic writes, structured logging), and AGENTS matrix maintenance.

### Prompt Chain governance
- Lifecycle, ruoli e fasi: vedi [`system/specs/promptchain_spec.md`](../specs/promptchain_spec.md) (SSoT).
- Active Rules, template e QA gates: vedi [`.codex/PROMPTS.md`](../../.codex/PROMPTS.md) e [`docs/policies/guida_codex.md`](../../docs/policies/guida_codex.md).
- Workflow OCP e gate: vedi [`docs/policies/OCP_WORKFLOW.md`](../../docs/policies/OCP_WORKFLOW.md).
-## Agency, Control Plane e ruolo dei micro-agent
- I riferimenti al flusso CLI o agli helper `pipeline.*` delineano gli strumenti della foundation: producono markdown semanticamente arricchiti e validano il knowledge graph ma NON orchestrano né decidono.
- La governance WHAT della Prompt Chain, del registry Intent/Action e delle escalation HiTL è descritta in `instructions/*`; ProtoTimmy/Timmy (agency) dialogano con Domain Gatekeepers (validazione) e il Control Plane/OCP applica i gate e la consegna ai micro-agent.
- I micro-agent (Codex incluso) eseguono i task sotto Work Order Envelope (OK / NEED_INPUT / CONTRACT_ERROR) come indicato da `instructions/`; mantengono trace e logging della pipeline senza assumere decisioni operative.

### Governance: non-fatal solo nella Prompt Chain
- **Perché ammesso:** nel dominio Prompt Chain l'errore è cognitivo (scopo, template, piano) e viene gestito da Evidence Gate + Skeptic Gate: OCP può imporre PASS/PASS WITH CONDITIONS/BLOCK e fermare la sequenza se le evidenze non sono complete.
- **Perché vietato nel runtime:** pipeline/semantic/storage/ui/metrics operano sul perimetro cliente; qui le failure infrastrutturali devono essere **strict** o almeno emettere segnali deterministici e tracciabili (log/eventi/exit code). La degradazione silenziosa è proibita.
- **Effetto sullo Skeptic Gate:** OCP tratta qualsiasi violazione di strictness runtime come condizione di BLOCK: la catena si ferma finché non esiste evidenza che l'errore sia gestito in modo esplicito e osservabile. Il non-fatal resta confinato alle fasi agentiche, mai al runtime.

---

## 2) Configuration: secrets vs versioned config

- **SSoT:** keep secrets outside the repo (`.env`), and versioned configuration inside `config/config.yaml`. Reference: [docs/configurazione.md](../../docs/configurazione.md).
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

References: [Developer Guide → Configuration](../../docs/developer/developer_guide.md), [Configuration Overview](../../docs/configurazione.md).

---

## 3) Security & path safety (mandatory)

- **Path safety:** route all I/O through `pipeline.path_utils.ensure_within*`.
- **Atomic writes:** use `pipeline.file_utils.safe_write_text/bytes` with temporary files and replacements.
- **Structured logging:** use `pipeline.logging_utils.get_structured_logger`, enabling redaction when `LOG_REDACTION` is active.
  - Log rotation is adjustable via `TIMMY_LOG_MAX_BYTES` and `TIMMY_LOG_BACKUP_COUNT`.
- Customer logs live in `output/timmy-kb-<slug>/logs/`; global UI logs are in `.timmy_kb/logs/`.
- The UI entrypoint writes `.timmy_kb/logs/ui.log` with shared handlers; Promtail augments logs with `run_id`, `trace_id`, and `span_id`.
  - `TIMMY_LOG_PROPAGATE` forces handler propagation; avoid console duplication by not overriding it unless required.
  - OTLP tracing uses `TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, and `TIMMY_ENV`.
- **Hashing & masking:** use `hash_identifier`/`sha256_path` with `TIMMY_HASH_SALT`, and prefer `mask_id_map` for sensitive extras.
- **RAW PDF cache:** `iter_safe_pdfs` uses an LRU cache controlled by config TTL and size; safe writes invalidate and preload caches.
- **Frontmatter caching:** post-write cache alignment with a 256-entry LRU; `semantic.api` clears caches after runs to avoid stale reuse.
- **UI import safety:** avoid import-time side effects; wrappers must keep signature parity with the backend.
- **Drive downloads:** UI downloads only missing PDFs. To overwrite, toggle "Overwrite conflicting local files" or manually rename files.
- **Preview stubs:** `PREVIEW_LOG_DIR` may point to absolute paths; if unreachable the preview fails explicitly (no fallback).
- **Ingest telemetry:** events such as `ingest.embed`, `ingest.persist`, `ingest.process_file`, `ingest.summary` must include `artifact_count`. Use these for dashboards and alerts.
- **Streaming ingest:** `ingest_folder` runs streaming globs with throttling controls (`max_files`, `batch_size`) to prevent OOM in migrations.

### Observability stack
- Config lives in `observability/docker-compose.yaml` and `observability/promtail-config.yaml`.
- Promtail monitors `../output/` and `../.timmy_kb/logs/`, tagging logs with `slug`, `run_id`, and `event`.
- Start locally with `docker compose up -d` inside `observability/`; Grafana listens on port 3000, Loki on 3100. Remember to map `output` and `.timmy_kb/logs` in Docker Desktop on Windows.
- Newer stack includes `tempo` (ports 3200/4317) and `otel-collector` (port 4318) for OTLP tracing.
- The UI log dashboard or `tools/observability_stack.py` can pulse the stack with the same env/compose files.

---

## 4) Operational flows (UI/CLI)

> Objective: turn PDFs into KB Markdown with coherent frontmatter, README/SUMMARY updates, and a HonKit Docker preview locale.

### Standard workflow
1. **pre_onboarding:** create the workspace (`output/timmy-kb-<slug>/...`), optionally provision Drive, and upload `config.yaml`.
2. **tag_onboarding:** produce `semantic/tags_raw.csv` and the HiTL checkpoint `tags_reviewed.yaml`.
3. **semantic_onboarding (via `semantic.api`):** convert PDFs to Markdown in `book/`, arricchire il frontmatter usando `semantic/tags.db` e ricostruire README/SUMMARY.
4. **honkit_preview (HonKit preview locale):** avvia la preview Docker su `book/`.

### UI gating
- Enable the Semantica tab only once local RAW data exists.
- Docker preview needs safe port validation and container naming.
- Telemetry event `semantic.book.frontmatter` tracks enriched file counts.

References: [.codex/WORKFLOWS.md](../../.codex/WORKFLOWS.md), [User Guide](../../docs/user/user_guide.md), [Architecture](../architecture.md).

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
- Delegated semantic pipeline steps call `semantic.convert_service`, `semantic.frontmatter_service`, and `semantic.embedding_service`; the `semantic.api` facade re-exports public helpers.
- NLP stages such as doc_terms/cluster go through `semantic.nlp_runner.run_doc_terms_pipeline` and `tag_onboarding.run_nlp_to_db`.
- Log every step; keep PRs/commits atomic and traceable.

### 5.4 Multi-agent alignment
- Ensure adapters (`ui.services.tags_adapter`, Drive services) load or that the UI shows stub help/fallback.
- Reset shared caches (`clients_store`, `safe_pdf_cache`) after atomic writes and log `reset_gating_cache`.

### 5.5 Prompt Chain execution
- Flow: User (Timmy/ProtoTimmy) → OrchestratoreChainPrompt (OCP) generates numbered prompts → OCP sends each prompt to Codex, who executes it as a micro-PR.
- Always start with the Onboarding Task Codex and respect the provided scope.
- Each step adheres to AGENT-first, HiTL, path safety, QA, and atomic writes. The OCP never edits the repo.
- Track every step in summaries/logs so the chain remains reproducible and idempotent.
- For governance details, refer to `system/specs/promptchain_spec.md`.

References: [AGENTS Index](agents_index.md), [.codex/AGENTS.md](../../.codex/AGENTS.md).

---

## 6) Quality, testing & CI

- Test pyramid: units → contract/middle → smoke E2E (dummy datasets, no network).
- Pre-commit hooks run formatters/linters (`isort`, `black`, `ruff --fix`), typechecks (`mypy`/`pyright`), spell-check (`cspell`), and guard rails (`forbid-*`).
- Rapid local CI: `make qa-safe` → `make ci-safe` → `pytest -q`.

### Required checks
- Reject invalid slugs or normalize them.
- Deny traversal via symlinks in `raw/`.
- Maintain UI/backend wrapper parity and parameter pass-through.
- Keep `book/` invariants: `README.md`/`SUMMARY.md` must exist; `.md.fp` files restano fuori dalla build.

References: [Developer Guide → Test](../../docs/developer/developer_guide.md), [Coding Rules → Test & Quality](../../docs/developer/coding_rule.md), [.codex/CHECKLISTS](../../.codex/CHECKLISTS.md).

---

## 7) Telemetry & operational security

- Centralize logs in `output/timmy-kb-<slug>/logs/` using key=value format.
- Automatically redact secrets by setting `LOG_REDACTION=1`.
- Use health-check scripts and hooks (`fix-control-chars`, `forbid-control-chars`) to manage characters/encoding.
- Throttle retriever queries: emit a warning (`retriever.throttle.deadline`) when budgets are depleted and clamp `candidate_limit`.

References: [README → Telemetry & Security](../README.md), [User Guide → Character Checks](../../docs/user/user_guide.md).

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

## 9) Governance & AGENTS matrix

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

References: (src/ui/AGENTS.md not present under src/ui), (src/ui/pages/AGENTS.md not present under src/ui/pages), [User Guide → UI](../../docs/user/user_guide.md).

---

## 13) Vision statement & AI tooling

- `tools/gen_vision_yaml.py` generates `semantic/semantic_mapping.yaml` from `config/VisionStatement.pdf`.
- UI always reads the model from `config/config.yaml` via `get_vision_model()` (SSoT).
- Prefer the Agent scenario; allow Full Access only with explicit justification and on a dedicated branch.
- `tools/vision_alignment_check.py` exports assistant metadata for diagnostics and logs.
- `use_kb` follows SSoT settings with optional overrides (`VISION_USE_KB`) for File Search gating.

References: [User Guide → Vision Statement](../../docs/user/user_guide.md), [Developer Guide → Configuration](../../docs/developer/developer_guide.md).

---

## 14) Operational checklists (excerpt)

- PR/Commit: conventional messages, updated tests, zero cSpell warnings.
- Security & I/O: path-safe ensures, atomic writes, defined rollback paths.
- UI/Workflow: gate Semantica, secure Docker preview, maintain `semantic/tags.db`.
- Drive: credenziali pronte per provisioning e sync.
- Documentation (blocking): update Architecture/Developer Guide/User Guide (and `.codex/WORKFLOWS.md` when pipeline changes) and list the updates in the PR's `Docs:` section.

References: [.codex/CHECKLISTS](../../.codex/CHECKLISTS.md).

---

## 15) Troubleshooting

- **Drive doesn't download PDFs:** regenerate the README in `raw/`, verify permissions and `DRIVE_ID`.
- **HonKit preview doesn't start:** check Docker and the port availability.
- **Conversion failures:** ensure valid PDFs exist within the allowed perimeter (avoid symlinks).
- **Spell-check/docs mismatch:** run cSpell on the docs and align frontmatter/title versions.
- **Model inconsistency:** check `config/config.yaml` and `get_vision_model()`.

References: [User Guide → Troubleshooting](../../docs/user/user_guide.md).

---

## 16) ADR & design changes

- Log architectural decisions as ADRs inside `docs/adr/`.
- Update the ADR index and link new documents; mark superseded entries accordingly.

References: [docs/adr/README.md](../../docs/adr/README.md).

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
streamlit run src/timmy_kb/ui/onboarding_ui.py

# CLI orchestrators
python -m timmy_kb.cli.pre_onboarding --slug <slug> --name "<Cliente>" --non-interactive
python -m timmy_kb.cli.tag_onboarding --slug <slug> --non-interactive --proceed
python -m timmy_kb.cli.tag_onboarding --slug <slug> --nlp --nlp-workers 6 --nlp-batch-size 8
python -m timmy_kb.cli.semantic_onboarding --slug <slug> --non-interactive
# Preview locale (HonKit/Docker)
# La preview è gestita via adapter/UI (vedi `src/adapters/preview.py`); il modulo esiste ma non è previsto/supportato come entrypoint pubblico `python -m pipeline.honkit_preview`.

# QA
make qa-safe
pytest -q
pre-commit run --all-files

# Spell & encoding
pre-commit run cspell --all-files
pre-commit run fix-control-chars --all-files
pre-commit run forbid-control-chars --all-files
```
