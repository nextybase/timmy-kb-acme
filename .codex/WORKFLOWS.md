# Operational Workflows (UI/CLI)

## Terminology (canonical)
All workflows in this folder execute within the **Agency Engine**.
They must not modify or bypass the **Epistemic Envelope**.

Canonical definitions and disambiguations are in:
- `.codex/CONSTITUTION.md` (normative entrypoint for `.codex/`)

Note: "Work Order Envelope" (used in prompt contracts) is an agent-level execution contract,
and is **not** the system-level Epistemic Envelope.

## Overview
- A dual approach offering both CLI orchestrators and the Streamlit UI (`onboarding_ui.py`).
- Goal: turn PDFs into AI-ready KB Markdown with coherent front matter, a synchronized README/SUMMARY, an HonKit Docker preview, .

### Codex Integration (Repo-aware, v2)
- Every UI/CLI workflow can also be executed through the repo-aware Codex agent, following `docs/codex_integrazione.md` and `system/ops/runbook_codex.md`.
- Each Codex-assisted execution must load the three mandated SSoT documents: `system/ops/agents_index.md`, the relevant area `AGENTS.md`, and `~/.codex/AGENTS.md`.
- The recommended entrypoint is the Onboarding Task Codex (see `.codex/PROMPTS.md`), which enforces a preliminary plan, idempotent micro-PRs, explicit QA, and AGENTS matrix updates.
- Workflows in this file must honor path safety, atomic writes, structured logging, and import-time safety even when driven by Codex.
- Every Prompt Chain follows `system/specs/promptchain_spec.md` as the single source of truth: Planner ? OCP ? Codex ? OCP ? Planner, Phase 0 (analytical/read-only), Phase 1..N (operational micro-PRs with intermediate QA), and Prompt N+1 (final QA plus narrative summary and an Italian one-line commit message).
- The Active Rules memo opens each operational prompt to remind teams about path safety ON, micro-PR discipline, zero side effects, documentation updates, the mandatory pre-check, intermediate QA (`python tools/test_runner.py fast`; ARCH only if invariants/contract/manifest change), final QA (`pre-commit run --all-files` + `pre-commit run --hook-stage pre-push --all-files`, fallback: `python tools/test_runner.py full`), and the Italian-only response policy; this memo enforces the template described in `.codex/PROMPTS.md`.
- Governance forbids skipping phases, executing multiple prompts per turn, or chaining prompts without Codex responses; after two failed autocorrections the agent must stop and ask the OCP for guidance.
- Operational prompts may touch only the files declared by the OCP, reference the SSoT documents in their reports, and document every QA attempt; the closing prompt runs the full QA stack before confirming completion.

### Static Patch Pre-Check
- Each Codex workflow starts with a static diff pre-check: forbid raw `open`, `Path` usage without path-utils, `_private` imports or forbidden wrappers, hardcoded paths, unstructured logging, REPO_ROOT/SSoT mutations, and non-atomic multi-topic patches; confirm the Active Rules memo is honored.
- The pre-check must complete before running QA; if it fails, do not launch tests, rewrite the patch using safe utilities, and repeat up to two attempts. After the third failure, pause and ask the OCP for guidance.
- Every intermediate Prompt Chain step must execute `python tools/test_runner.py fast` plus the mandated formatter/linter suite (ARCH only if invariants/contract/manifest change); the final prompt runs `pre-commit run --all-files` + `pre-commit run --hook-stage pre-push --all-files` for closure (fallback: `python tools/test_runner.py full`).

### Language Policy
- All conversational interactions between Codex, the OCP, and the user proceed in Italian by default; when the OCP dichiara control-mode, OCP ↔ Codex switches to English while Timmy/ProtoTimmy ↔ User stays Italian. Technical files and documentation may remain in English as required.

### Codex Smoke Chain - Diagnostic Test
- **Objective:** simulate a micro-cycle to confirm that turn-taking, memo awareness, QA interpretation, retry escalation, Italian-language policy, and pre-check validation all function without writing files.
- **Steps:**
  - S0: OCP issues a minimal prompt; Codex acknowledges the Active Rules memo.
  - S1: Codex describes the Pre-Check validation it would apply to a mock patch (no files created).
  - S2: OCP sends a sample operational prompt; Codex replies with a conceptual micro-PR narrative only.
  - S3: Codex states it would run `python tools/test_runner.py fast` and explains how it would interpret pass/fail results without executing the command.
  - S4: Codex spells out the escalation/retry plan (two autocorrections max) and reconfirms Italian-language compliance.
- **Rules:** no real patch, no disk I/O, no QA commands executed; treat it as a fast diagnostic after changing the Prompt Chain documentation.
- **Use cases:** governance health-check, post-update validation, and HiTL evidence that Codex and the OCP stay aligned.

## End-to-End Flow
1) **pre_onboarding** builds a local sandbox (`output/timmy-kb-<slug>/...`), optionally provisions Drive, and uploads `config.yaml` (no semantic templates copied).
2) **raw_ingest** normalizes RAW PDFs into `normalized/` and emits `normalized/INDEX.json`.
3) **tag_onboarding** generates `semantic/tags_raw.csv` (heuristic filenames/paths) and the HiTL checkpoint `tags_reviewed.yaml` for manual review.
4) **Tag KG Builder** (`kg_build.py` / UI Knowledge Graph) reads `semantic/tags_raw.json`, calls the OpenAI assistant `build_tag_kg`, saves `semantic/kg.tags.json` + `semantic/kg.tags.md`, and keeps a human-first inspection layer (watch namespaces).
5) **semantic_onboarding** (via `semantic.api` or CLI) converts normalized Markdown into `book/`, enriches front matter via the canonical `tags.db`, rebuilds README/SUMMARY, and prepares the Docker preview.
5) **honkit_preview** prepara e serve la preview Docker/HonKit di `book/`.

### UI Gating
- The Semantica tab appears only after `normalized/` is present locally.
- Docker preview: start/stop with a safe container name and port validation.
- Drive provisioning and onboarding workflows now depend solely on `ui.allow_local_only`: when the flag is `true` every Drive-related action (provisioning, cleanup, dummy generation, or UI controls) is skipped and treated as "local-only", and when it is `false` the preflight assumes Drive IDs/Service Account are already present without revalidating them at other layers. No other component should gate Drive actions outside of this flag-driven contract.

### Tag SSoT
- Human authoring relies on `semantic/tags_reviewed.yaml` as the review artifact.
- **Runtime** uses SQLite `semantic/tags.db` for orchestrators/UI enrichments.
- **Knowledge Graph** outputs `semantic/kg.tags.json` (machine-friendly) and `semantic/kg.tags.md` (human-readable) are built via `kg_build.py`/UI and consumed by future ingest/embedding steps.

### Invariants
- **Idempotence** (safe reruns) and **path safety** (all writes via dedicated utilities).
- **Structured logging** with redaction where required; portability across Windows/Linux.
- **Collector + Orchestrator patterns (UI refactor v2):** aggregator functions must be composable collectors, while the orchestrator keeps original order, outputs, and semantics (see preflight refactor).
- **Alignment with `.codex/PROMPTS.md`:** workflows triggered by Codex must apply the prompts defined therein (dependencies, path safety, QA, documentation/matrix updates) and stay within the perimeter defined in `system/ops/agents_index.md`.

## Semantic APIs Additions (v1)
These functions extend the semantic pipeline without altering UI/CLI flows. They remain idempotent, offline, path-safe, and employ atomic writes, allowing invocation from Codex workflows while honoring micro-PR and QA rules in `.codex/PROMPTS.md`.

- `build_mapping_from_vision(context, logger, slug) -> Path`: generates `semantic/semantic_mapping.yaml` from `output/timmy-kb-<slug>/config/visionstatement.yaml`. Input: vision YAML. Output: normalized mapping. Clear errors, no network.
- `build_tags_csv(context, logger, slug) -> Path`: scans `normalized/` (Markdown) and produces `semantic/tags_raw.csv` (conservative heuristics) plus `README_TAGGING.md`. Idempotent; CSV headers: `relative_path | suggested_tags | entities | keyphrases | score | sources`.
- `build_markdown_book(context, logger, slug) -> list[Path]`: converts RAW Markdown (one `.md` per top-level folder), ensures `README.md`/`SUMMARY.md` in `book/`. If `semantic/tags.db` is available, adds front matter enrichment (title/tags). Minimal fallback if helper repos are missing.
- `index_markdown_to_db(context, logger, slug, scope="book", embeddings_client, db_path) -> int`: indexes `.md` files into SQLite (one chunk per file, embeddings via `embeddings_client`). Metadata: `{file: <name>}`; daily versioned by `YYYYMMDD`. `db_path` must be provided explicitly (tests may pass a temporary absolute path within the workspace semantic dir).

Common invariants
- path safety via `pipeline.path_utils.ensure_within(...)` on outputs (and inputs where appropriate).
- Atomic writes through `pipeline.file_utils.safe_write_text/bytes`.
- Structured logging using `pipeline.logging_utils.get_structured_logger`.
