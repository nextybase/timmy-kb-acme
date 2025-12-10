# Operational Workflows (UI/CLI)

## Overview
- A dual approach offering both CLI orchestrators and the Streamlit UI (`onboarding_ui.py`).
- Goal: turn PDFs into AI-ready KB Markdown with coherent front matter, a synchronized README/SUMMARY, an HonKit Docker preview, and eventually a push to GitHub.

### Codex Integration (Repo-aware, v2)
- Every UI/CLI workflow can also be executed through the repo-aware Codex agent, following `docs/codex_integrazione.md` and `docs/runbook_codex.md`.
- Each Codex-assisted execution must load the three mandated SSoT documents: `docs/AGENTS_INDEX.md`, the relevant area `AGENTS.md`, and `~/.codex/AGENTS.md`.
- The recommended entrypoint is the Onboarding Task Codex (see `.codex/PROMPTS.md`), which enforces a preliminary plan, idempotent micro-PRs, explicit QA, and AGENTS matrix updates.
- Workflows in this file must honor path safety, atomic writes, structured logging, and import-time safety even when driven by Codex.
- Some workflows can be run inside a Prompt Chain orchestrated by the OCP: the entrypoint remains the Onboarding Task, and the prompt sequence is guided one-turn-at-a-time by the OCP without altering the baseline micro-PR + QA flow.
- `docs/PromptChain_spec.md` remains the single source of truth for the Prompt Chain: each OCP⇄Codex turn is strictly regulated (respond, stop, wait) and the closing step requires `pytest -q` plus `pre-commit run --all-files` before declaring the change set complete.
- Active Rules: each operational prompt begins with the memo that reminds teams about path safety ON, micro-PR discipline, zero side effects, documenting behavior changes, the pre-check, intermediate QA (`pytest -q -k "not slow"`), final QA (`pytest -q` + `pre-commit run --all-files`), and the Italian Language Policy; this header enforces the OCP?Codex turn-based cycle.
- Governance forbids chaining multiple OCP prompts without Codex responses; the cycle is OCP⇄Codex (response) ⇄ evaluation/feedback ⇄ next OCP prompt, with escalation after two failed correction attempts.
- Micro-PRs and QA are mandatory: each step is limited in scope, covered by intermediate QA, and the final prompt closes with full QA and escalation to the OCP if retries (max two autocorrections) do not succeed.

### Static Patch Pre-Check
- Each Codex workflow starts with a static diff pre-check: forbid raw `open`, `Path` usage without path-utils, `_private` imports or forbidden wrappers, hardcoded paths, unstructured logging, REPO_ROOT/SSoT mutations, and non-atomic multi-topic patches; confirm the Active Rules memo is honored.
- The pre-check must complete before running QA; if it fails, do not launch tests, rewrite the patch using safe utilities, and repeat up to two attempts. After the third failure, pause and ask the OCP for guidance.
- Every intermediate Prompt Chain step must execute the filtered QA `pytest -q -k "not slow"` plus the mandated formatter/linter suite; the final prompt runs the full `pytest -q` and `pre-commit run --all-files` for closure.

### Language Policy
- All conversational interactions between Codex, the OCP, and the user must proceed in Italian unless the prompt explicitly requests another language; technical files and documentation may remain in English as required.

### Codex Smoke Chain - Diagnostic Test
- **Objective:** simulate a micro-cycle to confirm that turn-taking, memo awareness, QA interpretation, retry escalation, Italian-language policy, and pre-check validation all function without writing files.
- **Steps:**
  - S0: OCP issues a minimal prompt; Codex acknowledges the Active Rules memo.
  - S1: Codex describes the Pre-Check validation it would apply to a mock patch (no files created).
  - S2: OCP sends a sample operational prompt; Codex replies with a conceptual micro-PR narrative only.
  - S3: Codex states it would run `pytest -q -k "not slow"` and explains how it would interpret pass/fail results without executing the command.
  - S4: Codex spells out the escalation/retry plan (two autocorrections max) and reconfirms Italian-language compliance.
- **Rules:** no real patch, no disk I/O, no QA commands executed; treat it as a fast diagnostic after changing the Prompt Chain documentation.
- **Use cases:** governance health-check, post-update validation, and HiTL evidence that Codex and the OCP stay aligned.

## End-to-End Flow
1) **pre_onboarding** builds a local sandbox (`output/timmy-kb-<slug>/...`), resolves the YAML definition, optionally provisions Drive, and uploads `config.yaml`.
2) **tag_onboarding** generates `semantic/tags_raw.csv` (heuristic filenames/paths) and the HiTL checkpoint `tags_reviewed.yaml` for manual review.
3) **Tag KG Builder** (`kg_build.py` / UI Knowledge Graph) reads `semantic/tags_raw.json`, calls the OpenAI assistant `build_tag_kg`, saves `semantic/kg.tags.json` + `semantic/kg.tags.md`, and keeps a human-first inspection layer (watch namespaces).
4) **semantic_onboarding** (via `semantic.api` or CLI) converts PDFs to Markdown in `book/`, enriches front matter via the canonical `tags.db`, rebuilds README/SUMMARY, and prepares the Docker preview.
5) **onboarding_full** runs preflight for Markdown files in `book/` and performs the GitHub push.

### UI Gating
- The Semantica tab appears only after the local RAW data (`raw/`) is downloaded.
- Docker preview: start/stop with a safe container name and port validation.

### Tag SSoT
- Human authoring relies on `semantic/tags_reviewed.yaml` as the review artifact.
- **Runtime** uses SQLite `semantic/tags.db` for orchestrators/UI enrichments.
- **Knowledge Graph** outputs `semantic/kg.tags.json` (machine-friendly) and `semantic/kg.tags.md` (human-readable) are built via `kg_build.py`/UI and consumed by future ingest/embedding steps.

### Invariants
- **Idempotence** (safe reruns) and **path safety** (all writes via dedicated utilities).
- **Structured logging** with redaction where required; portability across Windows/Linux.
- **Collector + Orchestrator patterns (UI refactor v2):** aggregator functions must be composable collectors, while the orchestrator keeps original order, outputs, and semantics (see preflight refactor).
- **Alignment with `.codex/PROMPTS.md`:** workflows triggered by Codex must apply the prompts defined therein (dependencies, path safety, QA, documentation/matrix updates) and stay within the perimeter defined in `docs/AGENTS_INDEX.md`.

## Semantic APIs Additions (v1)
These functions extend the semantic pipeline without altering UI/CLI flows. They remain idempotent, offline, path-safe, and employ atomic writes, allowing invocation from Codex workflows while honoring micro-PR and QA rules in `.codex/PROMPTS.md`.

- `build_mapping_from_vision(context, logger, slug) -> Path`: generates `config/semantic_mapping.yaml` from `config/vision_statement.yaml`. Input: vision YAML. Output: normalized mapping. Clear errors, no network.
- `build_tags_csv(context, logger, slug) -> Path`: scans `raw/` (PDF) and produces `semantic/tags_raw.csv` (conservative heuristics) plus `README_TAGGING.md`. Idempotent; CSV headers: `relative_path | suggested_tags | entities | keyphrases | score | sources`.
- `build_markdown_book(context, logger, slug) -> list[Path]`: converts RAW Markdown (one `.md` per top-level folder), ensures `README.md`/`SUMMARY.md` in `book/`. If `semantic/tags.db` is available, adds front matter enrichment (title/tags). Minimal fallback if helper repos are missing.
- `index_markdown_to_db(context, logger, slug, scope="book", embeddings_client, db_path=None) -> int`: indexes `.md` files into SQLite (one chunk per file, embeddings via `embeddings_client`). Metadata: `{file: <name>}`; daily versioned by `YYYYMMDD`. `db_path` allows isolated storage in tests.

Common invariants
- path safety via `pipeline.path_utils.ensure_within(...)` on outputs (and inputs where appropriate).
- Atomic writes through `pipeline.file_utils.safe_write_text/bytes`.
- Structured logging using `pipeline.logging_utils.get_structured_logger`.
