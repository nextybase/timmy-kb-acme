# Artifacts Policy (Core vs Service) - v1.0 Beta

## Scope & intent
This policy defines what an "artifact" represents in the Timmy-KB system and establishes the normative rules that govern determinism, fallback behavior, optional dependencies, and traceability.

It is a **normative Single Source of Truth (SSoT)**. In case of conflict with `docs/` or `system/`, this document prevails.

## Definitions

### Artifact
An artifact is any tangible output produced by the pipeline/UI/CLI (file, snapshot, index, ledger entry, report, etc.) that downstream actors (human or automated) may consume.

### Core Artifact (Epistemic Envelope output)
A core artifact:
- is required or implied by the foundation pipeline phases;
- is consumed by later steps as a deterministic input;
- belongs to the audit/lineage/ledger trail or the KB foundation.

Typical examples (non-exhaustive): `normalized/`, `book/README.md`, `book/SUMMARY.md`, `semantic/tags.db`, knowledge graph snapshots, ledger/lineage records.

### Service Artifact (Support / UX / Tooling)
A service artifact:
- supports UX, diagnostics, packaging, preview, or operational tooling;
- is not a prerequisite for the deterministic pipeline;
- must not alter or replace the semantics of core artifacts.

Examples: zipped logs, workspace summaries, in-memory cache, previews, "service" reports.

### INSTANCE_GLOBAL state store (service-only)
An `INSTANCE_GLOBAL` state store:
- is scoped to the running instance/project (not to a single customer workspace);
- may live at repo root (for example under `clients_db/`);
- is never an Epistemic Envelope artifact and never a pipeline/ledger prerequisite.

### TRANSIENT state store
A `TRANSIENT` state store:
- exists only for a bounded lifecycle (for example ProtoTimmy/UI onboarding);
- must be dismissible after the lifecycle transition (ProtoTimmy -> Timmy);
- must not become a runtime dependency for envelope phases.

### Clients Registry (formal classification)
`clients_db/clients.yaml` (and related `clients_db/*` UI state files) are classified as:
- `SERVICE_ONLY`
- `INSTANCE_GLOBAL`
- `TRANSIENT`

They support ProtoTimmy/UI multi-client onboarding only, are outside workspace scope by design, and must not drive deterministic pipeline outputs.

### Conditional CORE artifact
Some artifacts are CORE **only when** a capability or pipeline stage is active. In those situations:
- if the condition is active and the artifact is missing → FAIL-FAST (no fallback);
- if the condition is inactive → the artifact is **not required** and **must not** be produced implicitly.

"Conditional CORE" does **not** justify best-effort behaviors while the condition is active; the capability must explicitly govern the artifact's presence.

### Core-Gate Artifact (Gate prerequisite)
A core-gate artifact:
- serves as the normative prerequisite to unlock the production of further core artifacts;
- may reside in `logs/`, but is treated as CORE for gate evaluation;
- introduces no fallback or downgrade paths: if it is missing, the gate blocks.

## Beta invariants (strict)

### 1) Core artifacts MUST be deterministic
Core artifacts must be reproducible given the same inputs and configuration. Best-effort dependencies or alternative outputs that change format/semantics are forbidden.

### 2) No silent downgrade for core artifacts
When a core artifact relies on an optional dependency or capability that is unavailable, the only allowed behavior is:
- STOP with a typed error (fail-fast), and
- explicit tracking (structured log and ledger entry where applicable).

Automatically substituting a core artifact with a "good enough" variant (e.g., emitting `.txt` instead of `.pdf`, or changing the format without explicit authorization) is prohibited.

### 3) Service artifacts MAY be best-effort (but must not masquerade)
Service artifacts are allowed to follow best-effort or fallback behavior only under the following conditions:
- they do not alter or replace core artifacts;
- they are explicit (structured log) and marked as "SERVICE_ONLY";
- they do not introduce implicit dependencies for subsequent steps.
- "best-effort" applies to the artifact outcome, not to missing required infrastructure dependencies (for example PyYAML), which remain fail-fast.

### 3bis) Controlled exception: instance-global UI state stores
Workspace remains the only perimeter for Envelope/Pipeline/Ledger artifacts.
Controlled exception: `SERVICE_ONLY` UI state stores may live outside workspace when all conditions hold:
- explicitly classified as `INSTANCE_GLOBAL` and `TRANSIENT`;
- no influence on deterministic pipeline, gate decisions, or ledger lineage;
- no runtime dependency introduced for envelope phases.

### Determinism & Observability (P1)
CORE artifacts MUST be deterministic and reproducible at parity of inputs, configuration, and capability flags.
Any time-variant telemetry, timestamps, or cache state are SERVICE artifacts and MAY vary; they MUST NOT influence gating, ordering, or selection of CORE inputs.
SERVICE-only supporting artifacts MUST be marked as such (structured log + `service_only` flag) so they cannot masquerade as deterministically required outputs.
Note: the Vision audit log append is the single strict guard for SERVICE observability--failures emit `semantic.vision.audit_write_failed` only when `service_only=True`, while the retention/`purge_old_artifacts` path remains SERVICE-only best-effort and MUST NOT block CORE generations (it simply logs what it cleans without gating the pipeline).

### 4) Optional dependencies policy
Optional dependencies are permitted only when:
- they are enabled through explicit capability gating (configuration or documented extra), and
- their failure does not create apparent "success" for the affected core artifacts.

### 5) Time-based state and caching policy
Any time-based cache (TTL, wall-clock timestamps) counts as *operational entropy*. These caches are acceptable only as service behavior when:
- they do not influence decisions, ordering, or selection of pipeline inputs;
- they are not used to produce or skip core artifacts;
- they remain confined to performance/UX and do not mutate persistent artifacts.

If a time-based cache is pre-warmed automatically, it must stay invisible to semantics and must not become an implicit requirement.

### 6) QA evidence is CORE-GATE (`README/SUMMARY`)
`logs/qa_passed.json` is a **core-gate artifact** and a normative prerequisite to generate `book/README.md` and `book/SUMMARY.md`.
Its absence or corruption blocks the gate.

The `timestamp` field may exist as telemetry, but it **must not** be part of the deterministic comparison between core artifacts.

### 7) CORE observability (metrics/logging/telemetry)
Metrics and logging/telemetry channels are classified as **CORE observability** controls.

CORE observability must not:
- alter core artifacts or their semantics;
- change gate outcomes or process selection logic;
- interrupt operational flow when telemetry emission fails.

Allowed behavior on telemetry emission failure is **surface once**:
- emit one explicit structured error event for diagnosability;
- suppress repeated equivalent errors to avoid noise flood;
- do not introduce fallback paths that modify process behavior.

### Service-only utilities & entropy guards
The Epistemic Envelope perimeter (pipeline deterministic core, semantic core, storage, ledger) does not allow silent fallbacks.

`return []` is allowed only when it represents a legitimate semantic "no data" outcome; it is not allowed as exception masking.

`SERVICE_ONLY` modules (for example UI utilities, observability support, and retriever CLI best-effort helpers) may use controlled fallback behaviors only when:
- they do not produce/replace Envelope artifacts;
- they do not affect deterministic gate decisions or ledger lineage;
- they are explicitly classified as service-only.

`tests/architecture/test_entropy_guards.py` enforces this distinction: strict checks on Envelope/core runtime, controlled exceptions for service-only modules.

## Classification rule (practical)
When a module produces a file:
- if the file ends up in a pipeline directory (workspace layout) or is cited as a prerequisite → treat it as CORE (or CORE-GATE when it gates);
- if it serves diagnostics, packaging, preview, or UI exports → treat it as SERVICE.

When unsure: default to CORE.

## Compliance hooks (normative expectations)
- Gatekeepers and micro-agents (Work Order Envelope) must treat any unauthorized alternative production of core artifacts as a violation.
- An "OK" verdict is invalid if the expected core artifacts were not produced in the required form.

## Allowed exceptions (strictness/caching)
No active exceptions (2026-01-25).

Any use of:
- `sanitize_filename(..., strict=False)` or `allow_fallback=True`, or
- `iter_safe_pdfs(..., use_cache=True)` or TTL-based selection/order cache

must be listed here with motivation and dedicated tests.

## Runtime Rules
- Core artifacts must be produced deterministically.
- The absence or corruption of a core artifact blocks the pipeline (fail-fast) and must be tracked.
- Silent fallback or downgrade behavior is not allowed.
- For conditional CORE artifacts:
  - "Skip with warning" is not valid while the condition is active.
  - The condition must be explicit and verifiable (no heuristic fallback).

### Corruption Handling (P3)
Any corruption in `kb.sqlite`, including invalid JSON in meta or embedding fields, is treated as CORE artifact corruption.
In strict execution such failures MUST hard-fail the pipeline.
In non-strict/UX flows the corrupted rows MAY be skipped only when the skip is observable (structured log marked SERVICE_ONLY) and does not influence the deterministic production of downstream CORE artifacts.
The non-strict exception exists solely for resilience: skipping corrupted rows is acceptable provided the resulting CORE artifacts downstream remain identical, the skip is logged with `service_only=True`, and operators can audit which row(s) were skipped so the policy degradation stays visible.

## Notes
- Workspace artifacts are validated based on the configuration of the active capabilities.
- Artifacts required by inactive capabilities must not be forced.
- Clarification: the presence of a conditional CORE artifact does not activate a capability; capabilities activate artifacts.

## Appendix A - Runtime inventory (`src/`)
Method: static scan of producers in `src/` (runtime UI/CLI/pipeline). Excludes `tools/` and `tests/`.
Includes file/DB/log/zip writes identified via `safe_write_*`, sqlite3, log handlers, and zip utilities.
Limit: dynamic writes through plugins/ENV may not be captured by the scan.

Legend: CORE = deterministic pipeline artifact; CORE-GATE = normative prerequisite for unlocking core; SERVICE = support/UX/diagnostics.

### A.1 Workspace & config
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/workspace_bootstrap.py:bootstrap_client_workspace`<br>`bootstrap_dummy_workspace`<br>`migrate_or_repair_workspace` | `output/timmy-kb-<slug>/config/config.yaml`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | YAML + Markdown | `pipeline.context`, `WorkspaceLayout`, UI/CLI | CORE | Template `config/config.yaml` | No (fail-fast if template missing) |
| `src/pipeline/workspace_bootstrap.py:bootstrap_client_workspace`<br>`bootstrap_dummy_workspace`<br>`migrate_or_repair_workspace` | `output/timmy-kb-<slug>/{raw,normalized,semantic,book,logs,config}/` | Workspace directories | `WorkspaceLayout`, UI/CLI | CORE | FS permissions | No (fail-fast on file system errors) |
| `src/pipeline/context.py:_ensure_config` | `output/timmy-kb-<slug>/config/config.yaml` | YAML | `Settings.load`, UI/CLI | CORE | Template `config/config.yaml` | No (fail-fast if template missing) |
| `src/pipeline/config_utils.py:write_client_config_file`<br>`merge_client_config_from_template`<br>`update_config_with_drive_ids` | `output/timmy-kb-<slug>/config/config.yaml` | YAML | Pipeline/CLI/UI | CORE | PyYAML, path safety | No (fail-fast on errors) |
| `src/pipeline/config_utils.py:write_client_config_file`<br>`merge_client_config_from_template` | `output/timmy-kb-<slug>/config/config.yaml.bak` | Backup YAML | Operator (rollback) | SERVICE | FS copy | No (error if backup fails) |
| `src/ui/config_store.py:_save_repo_config`<br>`_save_config`<br>`src/ui/pages/configurazione.py:_write_config` | `config/config.yaml` | YAML | `Settings.load`, UI/CLI | CORE | PyYAML | No (fail-fast on errors) |
| `src/ui/pages/new_client.py:_mirror_repo_config_into_client`<br>`src/timmy_kb/cli/pre_onboarding.py:ensure_local_workspace_for_ui` | `output/timmy-kb-<slug>/config/config.yaml` | YAML | Pipeline/CLI/UI | CORE | PyYAML, template config | No (fail-fast on errors) |
| `src/timmy_kb/cli/pre_onboarding.py:ensure_local_workspace_for_ui` | `output/timmy-kb-<slug>/config/assistant_vision_system_prompt.txt` | TXT prompt | Vision provisioning | CORE (conditional) | Source `config/assistant_vision_system_prompt.txt` | Condition:<br>- required **only** when Vision capability is active (Vision assistant in strict/structured output);<br>Behavior:<br>- if Vision is active and the prompt is missing or empty → FAIL-FAST (ConfigError / PipelineError).<br>- if Vision is inactive → the artifact is not required and is not synthesized implicitly.<br>Notes:<br>- the workspace version (if present) is a SERVICE artifact and must not influence runtime when Vision is inactive. |
| `src/ui/pages/new_client.py`<br>`src/timmy_kb/cli/pre_onboarding.py:ensure_local_workspace_for_ui` | `output/timmy-kb-<slug>/config/VisionStatement.pdf` | PDF | `visionstatement.yaml` + mapping | CORE (conditional) | User upload | No (missing file blocks Vision) |
| `src/ui/fine_tuning/vision_modal.py:_ensure_workspace_pdf` | `output/timmy-kb-<slug>/config/VisionStatement.pdf` | PDF | UI Vision modal | CORE (conditional) | None | No (missing file blocks Vision) |

### A.2 Vision & mapping
Note: `visionstatement.yaml` exists only in the workspace (`output/timmy-kb-<slug>/config/visionstatement.yaml`); the repo root keeps `config/vision_template.yaml` as the contract.
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/semantic/core.py:compile_document_to_vision_yaml` | `output/timmy-kb-<slug>/config/visionstatement.yaml` | YAML (vision) | `semantic.vision_provision`, `pipeline.vision_runner`, UI Vision | CORE | PyYAML, PDF extraction | No (fail-fast on error) |
| `src/semantic/vision_provision.py:_persist_outputs` | `output/timmy-kb-<slug>/semantic/semantic_mapping.yaml` | YAML mapping | Tagging/Semantics | CORE | Vision responses, valid schema | No |
| `src/ui/components/mapping_editor.py:save_semantic_mapping`<br>`src/ui/components/yaml_editors.py:_write_yaml_text` | `output/timmy-kb-<slug>/semantic/semantic_mapping.yaml` | YAML mapping | Tagging/Semantics | CORE | UI + valid YAML | No |
| `src/ui/components/mapping_editor.py:write_raw_structure_yaml` | `output/timmy-kb-<slug>/semantic/_raw_from_mapping.yaml` | YAML (raw layout) | Drive runner (optional) | SERVICE | Mapping exists | No |
| `src/semantic/vision_provision.py:_write_audit_line` | `output/timmy-kb-<slug>/logs/semantic.vision.log` | JSONL audit log | Diagnostics | SERVICE | FS write | `best-effort (SERVICE_ONLY)` - failures log `semantic.vision.audit_write_failed` (append failure) or `semantic.vision.audit_lock_cleanup_failed` (lock cleanup failure) with `scene=service`, `service_only=True`, `service=semantic.vision.audit_log`; documented coverage: `tests/semantic/test_vision_audit_service.py` + `tests/contract/test_service_audit_log.py`. |
| `src/ai/responses.py:_diagnose_json_schema_format` | `output/debug/vision_schema_sent.json` | Debug JSON | Diagnostics | SERVICE | Local debug | Yes (best-effort, warning on failure) |

### A.3 Raw ingest
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/drive/download.py:download_drive_pdfs_to_local`<br>`src/pipeline/ingest/provider.py:DriveIngestProvider.ingest_raw` | `output/timmy-kb-<slug>/raw/<category>/<file>.pdf` | PDF (raw) | Raw ingest | CORE (conditional) | Drive capability + googleapiclient | No (fail-fast) |
| `src/semantic/tags_extractor.py:copy_local_pdfs_to_raw`<br>`src/pipeline/ingest/provider.py:LocalIngestProvider.ingest_raw` | `output/timmy-kb-<slug>/raw/<rel>.pdf` | PDF (raw) | Raw ingest | CORE (conditional) | Local FS | No |
| `src/pipeline/vision_runner.py:_materialize_raw_structure` | `output/timmy-kb-<slug>/raw/<area>/` | Directory structure | Drive/local ingest | CORE (conditional) | `semantic/semantic_mapping.yaml` | No (fail-fast if mapping invalid) |
| `src/pipeline/raw_transform_service.py:PdfTextTransformService.transform` | `output/timmy-kb-<slug>/normalized/<rel>.md` | Normalized Markdown | Tagging/Semantics | CORE | `nlp.nlp_keywords.extract_text_from_pdf` | No (fail-fast if dependency missing) |
| `src/pipeline/normalized_index.py:write_index` | `output/timmy-kb-<slug>/normalized/INDEX.json` | JSON index | Raw ingest gating | CORE | JSON serialization | No |

### A.4 Tagging & vocabulary
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/semantic/auto_tagger.py:render_tags_csv` | `output/timmy-kb-<slug>/semantic/tags_raw.csv` | CSV suggestions | HiTL review | CORE | Mapping + normalized | No |
| `src/ui/manage/tags.py:handle_tags_raw_save` | `output/timmy-kb-<slug>/semantic/tags_raw.csv` | CSV | HiTL review | CORE | UI editor | No |
| `src/semantic/review_writer.py:write_review_stub` | `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | YAML review | Tagging/DB | CORE | Valid CSV | No |
| `src/semantic/tags_io.py:write_tags_reviewed_from_nlp_db` | `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | YAML review | Tagging/DB | CORE | `tags.db` present | No |
| `src/ui/manage/tags.py:open_tags_editor_modal`<br>`src/ui/components/yaml_editors.py:_write_yaml_text` | `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | YAML review | Tagging/DB | CORE | UI editor | No |
| `src/storage/tags_store.py:ensure_schema_v2`<br>`get_conn`/`upsert_*` | `output/timmy-kb-<slug>/semantic/tags.db` | SQLite DB | Semantics/frontmatter | CORE | sqlite3 | No (fail-fast on legacy) |
| `src/semantic/tags_io.py:write_tagging_readme` | `output/timmy-kb-<slug>/semantic/README_TAGGING.md` | Guideline Markdown | UX tagging | SERVICE | FS write | No |
| `src/semantic/tags_validator.py:write_validation_report` | `output/timmy-kb-<slug>/semantic/<report>.json` | JSON report | Diagnostics | SERVICE | JSON serialization | No |
| `src/timmy_kb/cli/kg_builder.py:_save_outputs`<br>`src/ui/services/tag_kg_builder.py:run_tag_kg_builder` | `output/timmy-kb-<slug>/semantic/kg.tags.json`<br>`output/timmy-kb-<slug>/semantic/kg.tags.md` | JSON + Markdown (KG) | Review/diagnostics | SERVICE | OpenAI assistant + `semantic/tags_raw.json` | Yes (skip if `tags_raw.json` missing upstream) |

### A.5 Semantic onboarding & book
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/semantic/convert_service.py:_write_markdown_for_normalized`<br>`src/pipeline/content_utils.py:convert_files_to_structured_markdown` | `output/timmy-kb-<slug>/book/<rel>.md` | Book Markdown | Preview/KB | CORE | normalized/*.md | No |
| `src/semantic/frontmatter_service.py:write_readme`<br>`src/pipeline/content_utils.py:generate_readme_markdown` | `output/timmy-kb-<slug>/book/README.md` | Markdown | Preview/KB | CORE | mapping + content (+ optional `layout_proposal.yaml`) | No |
| `src/semantic/frontmatter_service.py:write_summary`<br>`src/pipeline/content_utils.py:generate_summary_markdown` | `output/timmy-kb-<slug>/book/SUMMARY.md` | Markdown | Preview/KB | CORE | book/*.md | No |
| `src/semantic/frontmatter_service.py:_persist_layout_proposal` | `output/timmy-kb-<slug>/semantic/layout_proposal.yaml` | Proposal YAML | Diagnostics/UX | SERVICE | Vision text, PyYAML (required dependency) | Yes (best-effort on proposal generation/persist path; no fallback on missing required dependency) |
| `src/semantic/frontmatter_service.py:_write_layout_summary` | `output/timmy-kb-<slug>/book/layout_summary.md` | Markdown | UX/preview | SERVICE | `semantic/layout_proposal.yaml` | Yes (skip if layout missing) |

### A.6 DB, ledger, preview
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/kb_db.py:init_db`/`insert_chunks` | `output/timmy-kb-<slug>/semantic/kb.sqlite` | SQLite embeddings | Retriever | CORE (conditional) | sqlite3, embeddings client | No |
| `src/storage/decision_ledger.py:open_ledger`/`_init_schema` | `output/timmy-kb-<slug>/config/ledger.db` | SQLite ledger | Audit/lineage | CORE | sqlite3 | No |
| `src/pipeline/honkit_preview.py:ensure_book_json` | `output/timmy-kb-<slug>/book/book.json` | JSON config | Preview | SERVICE | HonKit preview | Yes (idempotent, only if missing) |
| `src/pipeline/honkit_preview.py:ensure_package_json` | `output/timmy-kb-<slug>/book/package.json` | JSON config | Preview | SERVICE | HonKit preview | Yes (idempotent, only if missing) |

### A.7 Logs, diagnostics, UI state
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/logging_utils.py:get_structured_logger` | `output/timmy-kb-<slug>/logs/onboarding.log`<br>`.timmy_kb/logs/ui.log` | Log file | Operator/diagnostics | SERVICE | FS write | Yes (console fallback) |
| `src/ui/pages/preview.py:_write_stub_log` | `logs/preview/<slug>.log` (or `PREVIEW_LOG_DIR`) | Stub log | UX preview | SERVICE | FS write | Yes (stub only) |
| `src/pipeline/qa_evidence.py:write_qa_evidence` | `output/timmy-kb-<slug>/logs/qa_passed.json` | QA JSON | QA gate → README/SUMMARY | CORE-GATE | JSON serialization | No |
| `src/ui/gating.py:write_gate_capability_manifest` | `output/timmy-kb-<slug>/logs/gate_capabilities.json` | JSON capability | UI gating | SERVICE | FS write | No |
| `src/explainability/serialization.py:safe_write_manifest`<br>`src/timmy_kb/cli/retriever_manifest.py:_write_manifest_if_configured` | `output/timmy-kb-<slug>/semantic/explainability/<response_id>.json` (configured base dir) | JSON manifest | Audit/lineage | SERVICE | Retriever + configured `explain_base_dir` | Yes (skip if base dir unset) |
| `src/ui/utils/diagnostics.py:build_logs_archive` | ZIP bytes (in-memory) + `workspace_summary.json` | ZIP report | Support | SERVICE | zipfile | Yes (best-effort, None on failure) |
| `src/pipeline/system_self_check.py:_check_output_writable` | `output/.selfcheck_tmp` | Probe file | Self-check | SERVICE | FS write | Yes (cleanup best-effort) |
| `src/pipeline/observability_config.py:update_observability_settings` | `~/.timmy_kb/observability.yaml` | YAML preferences | UI observability | SERVICE | PyYAML | No |
| `src/ui/clients_store.py:_save_registry` | `clients_db/clients.yaml` | YAML registry | UI/CLI | SERVICE | PyYAML | No |
| `src/ui/utils/slug.py:_save_persisted` | `clients_db/ui_state.json` | JSON state | UI | SERVICE | FS write | Yes (errors suppressed) |
| `src/ui/semantic_progress.py:_write_progress` | `clients_db/semantic_progress/<slug>.json` | JSON state | UI gating | SERVICE | JSON serialization | No |
| `src/pipeline/ownership.py:ensure_ownership_file` | `clients_db/clients/<slug>/ownership.yaml` | YAML ownership | UI/ACL | SERVICE | PyYAML | No |
| `src/ui/pages/agents_network.py:_save_agents_sections` | `AGENTS.md` / `system/ops/agents_index.md` | Governance Markdown | Governance UI | SERVICE | FS write | No |

### A.8 Drive (remote)
| Producer (file:function) | Path target | Output type | Consumer | Class | Dependency/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/drive/upload.py:create_drive_folder` | `Drive/<client_folder>/` | Drive folder | Provisioning/Drive ingest | CORE (conditional) | Drive APIs + credentials | No (fail-fast) |
| `src/pipeline/drive/upload.py:create_drive_minimal_structure` | `Drive/<client_folder>/{raw,contractual}/` | Drive folders | Ingest/contracts | CORE (conditional) | Drive APIs + credentials | No |
| `src/pipeline/drive/upload.py:upload_config_to_drive_folder` | `Drive/<client_folder>/config.yaml` | YAML (Drive) | Sync/operator | CORE (conditional) | Drive APIs + credentials | No |
| `src/pipeline/drive/upload.py:create_drive_structure_from_names` | `Drive/<client_folder>/raw/<area>/` | Drive folders | Raw ingest (Drive) | CORE (conditional) | Drive APIs + mapping | No (fail-fast if mapping invalid) |
| `src/ui/services/drive_runner.py:emit_readmes_for_raw` | `Drive/<client_folder>/raw/<area>/README.pdf`<br>`Drive/<client_folder>/raw/<area>/README.txt` | PDF/TXT | UX/operator | SERVICE | ReportLab (optional) | Yes (SERVICE_ONLY + structured log + Drive appProperties) |

## Appendix B - CORE artifacts expected per phase
| Phase (runbook) | Expected CORE artifacts | Notes/conditions |
| --- | --- | --- |
| pre_onboarding | `output/timmy-kb-<slug>/config/config.yaml`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | Idempotent bootstrap. If Vision is active: `output/timmy-kb-<slug>/config/VisionStatement.pdf`, `output/timmy-kb-<slug>/config/visionstatement.yaml`, `output/timmy-kb-<slug>/semantic/semantic_mapping.yaml`. |
| raw_ingest | `output/timmy-kb-<slug>/normalized/<rel>.md`<br>`output/timmy-kb-<slug>/normalized/INDEX.json` | Every file marked `OK` in INDEX must exist on disk. |
| tag_onboarding | `output/timmy-kb-<slug>/semantic/tags_raw.csv`<br>`output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | `tags.db` is CORE when the review is applied (sync/semantic enablement phase). |
| semantic_onboarding | `output/timmy-kb-<slug>/book/<rel>.md`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | Enrichment requires `semantic/tags.db` present and valid. `logs/qa_passed.json` is a CORE-GATE prerequisite for README/SUMMARY. |
| honkit_preview | No new CORE artifacts | Preview is SERVICE-only (`book.json`, `package.json`, preview log). |
| cross-phase (ledger) | `output/timmy-kb-<slug>/config/ledger.db` | CORE evidence: if the ledger is active, it must be written deterministically. |
