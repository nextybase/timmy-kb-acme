# QA Gate & Core Artifacts Recon (no code changes)

## Scope
- Ricognizione di writer/reader QA evidence, generatori README/SUMMARY, ArtifactPolicyViolation/Decision Record, e presenza di manifest deterministico.
- Solo evidenze oggettive con file+linee+snippet.

## 1) QA evidence (`qa_passed.json`) — writer/reader

### Writer (runtime)
- `src/pipeline/qa_evidence.py:107-126`
  - `write_qa_evidence(...)` scrive `qa_passed.json` con `safe_write_text` e payload ordinato.
  - Snippet: `safe_write_text(path, json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", ...)`
- `src/timmy_kb/cli/qa_evidence.py:48-62`
  - CLI esegue `pre-commit` + `pytest -q`, poi `write_qa_evidence(..., qa_status="pass"|"fail")`.
  - Snippet: `write_qa_evidence(layout.log_dir, checks_executed=checks_executed, qa_status="pass", ...)`

### Reader (runtime)
- `src/pipeline/qa_gate.py:24-63`
  - `require_qa_gate_pass(log_dir)` è la fonte unica: carica/valida evidence e decide PASS/FAIL.
- `src/ui/pages/semantics.py:289-326`
  - UI chiama `require_qa_gate_pass(...)` prima di `write_summary_and_readme`.

### Writer/reader (test)
- `tests/ui/test_semantics_state.py:29-37`
  - Helper test che scrive `qa_passed.json` (timestamp fisso).
  - Snippet: `path.write_text(json.dumps(payload) + "\n", encoding="utf-8")`

### Classificazione policy
- `instructions/13_artifacts_policy.md:171`
  - `qa_passed.json` classificato **CORE-GATE**.

## 2) Generazione `book/README.md` e `book/SUMMARY.md` (UI + CLI)

### Generatori base (writer effettivi)
- `src/pipeline/content_utils.py:579-658`
  - `generate_readme_markdown(...)` → scrive `book/README.md`.
  - Snippet: `readme = target / "README.md"` + `safe_write_text(readme, ...)`
- `src/pipeline/content_utils.py:662-697`
  - `generate_summary_markdown(...)` → scrive `book/SUMMARY.md`.
  - Snippet: `summary = target / "SUMMARY.md"` + `safe_write_text(summary, ...)`
- `src/semantic/frontmatter_service.py:433-491`
  - `write_summary_and_readme(...)` richiama `_gen_summary` + `_gen_readme`.
  - Snippet: `summary_func(paths)` e `readme_func(paths)` + log `semantic.summary.written`, `semantic.readme.written`

### UI path
- `src/ui/pages/semantics.py:269-350`
  - `_run_summary` chiama `require_qa_gate_pass(...)` e poi `write_summary_and_readme(...)`.

### CLI path
- `src/semantic/frontmatter_service.py:433-491`
  - `write_summary_and_readme(...)` chiama `require_qa_gate_pass(...)`.
- `src/semantic/api.py:234-265`
  - `run_semantic_pipeline` → `_run_build_workflow` → `write_summary_and_readme`.
- `src/timmy_kb/cli/semantic_onboarding.py:231-238`
  - `run_semantic_pipeline(...)` in CLI semantic onboarding.
- `src/timmy_kb/cli/semantic_headless.py:42-74`
  - Headless pipeline chiama direttamente `write_summary_and_readme(...)`.

### Bootstrap / riparazione (scrive README/SUMMARY)
- `src/pipeline/workspace_bootstrap.py:58-63`
  - `bootstrap_client_workspace` crea README/SUMMARY minimali.
  - Snippet: `_write_minimal_file(book_dir / "README.md", ...)`
- `src/pipeline/workspace_bootstrap.py:133-135`
  - `bootstrap_dummy_workspace` crea README/SUMMARY minimali.
- `src/pipeline/workspace_bootstrap.py:168-174`
  - `migrate_or_repair_workspace` (repair) riscrive README/SUMMARY.

### Validazione (non writer)
- `src/pipeline/workspace_layout.py:270-275`
  - Richiede presenza di README/SUMMARY nel layout.

## 3) ArtifactPolicyViolation / Decision Record / decision_ledger

### Eccezione e stop_code
- `src/pipeline/exceptions.py:215-226`
  - `ArtifactPolicyViolation` con `evidence_refs`.
- `src/storage/decision_ledger.py:55-59`
  - `STOP_CODE_ARTIFACT_POLICY_VIOLATION = "ARTIFACT_POLICY_VIOLATION"`

### Policy enforcement (core artifacts)
- `src/pipeline/artifact_policy.py:46-129`
  - `enforce_core_artifacts` include `book/README.md` + `book/SUMMARY.md`.
- `src/timmy_kb/cli/raw_ingest.py:186-217`
  - `enforce_core_artifacts("raw_ingest")` → `ArtifactPolicyViolation` → `record_normative_decision(... STOP_CODE_ARTIFACT_POLICY_VIOLATION)`

### Mapping stop_code in CLI
- `src/timmy_kb/cli/pre_onboarding.py:207-214`
  - `_normative_verdict_for_error` mappa `ArtifactPolicyViolation` → `STOP_CODE_ARTIFACT_POLICY_VIOLATION`.
- `src/timmy_kb/cli/tag_onboarding.py:131-138`
  - `_normative_verdict_for_error` mappa `ArtifactPolicyViolation` → `STOP_CODE_ARTIFACT_POLICY_VIOLATION`.
- `src/timmy_kb/cli/semantic_onboarding.py:110-117`
  - `_normative_verdict_for_error` mappa `ArtifactPolicyViolation` → `STOP_CODE_ARTIFACT_POLICY_VIOLATION`.
  - `_normative_verdict_for_error` mappa `QaGateViolation` → `STOP_CODE_QA_GATE_FAILED`.

### Decision Record (ledger) emissione
- `src/storage/decision_ledger.py:198-231`
  - `record_normative_decision(...)` costruisce `evidence_json` con `evidence_refs` e `stop_code`.
- `src/timmy_kb/cli/tag_onboarding.py:633-673`
  - `record_normative_decision(...)` su gate `tag_onboarding`.
- `src/timmy_kb/cli/semantic_onboarding.py:260-356`
  - `record_normative_decision(...)` su gate `semantic_onboarding`.
- `src/timmy_kb/cli/raw_ingest.py:190-239`
  - `record_normative_decision(...)` su gate `normalize_raw`.

## 4) Manifest deterministico / golden manifest
- `tests/architecture/test_determinism_low_entropy_gate.py:65-81`
  - Genera manifest con hash/bytes di `config/config.yaml`, `book/README.md`, `book/SUMMARY.md`.
  - Snippet: `manifest = {"schema_version": 1, "artifacts": artifacts}`
- `tests/fixtures/determinism_manifest.json:1`
  - Fixture golden manifest.

## 5) Mappa “UI path” e “CLI path”

### UI path (QA gate → README/SUMMARY)
- `ui.pages.semantics._run_summary` → `require_qa_gate_pass` → `write_summary_and_readme`.
  - Evidenze: `src/ui/pages/semantics.py:289-350`, `src/pipeline/qa_gate.py:24-63`.

### CLI path (README/SUMMARY)
- `semantic_onboarding` → `run_semantic_pipeline` → `write_summary_and_readme` (chiama `require_qa_gate_pass`) → `generate_*`.
  - Evidenze: `src/timmy_kb/cli/semantic_onboarding.py:231-238`, `src/semantic/api.py:234-265`,
    `src/semantic/frontmatter_service.py:433-491`, `src/pipeline/qa_gate.py:24-63`.
- `semantic_headless` → `write_summary_and_readme` (chiama `require_qa_gate_pass`) → `generate_*`.
  - Evidenze: `src/timmy_kb/cli/semantic_headless.py:42-74`, `src/semantic/frontmatter_service.py:433-491`.

## 6) Punti di divergenza attuali (osservazioni oggettive)
- Nessuna divergenza rilevata tra UI e CLI: entrambi usano `require_qa_gate_pass(...)` come precondizione.

## 7) Dipendenze e side effects (timestamp, path, logs)
- QA evidence payload include timestamp wall-clock:
  - `src/pipeline/qa_evidence.py:47-55` (`datetime.now(timezone.utc).isoformat()`).
- CLI QA evidence esegue comandi esterni:
  - `src/timmy_kb/cli/qa_evidence.py:48-57` (`pre-commit run --all-files`, `pytest -q`).
- QA evidence write log strutturato:
  - `src/pipeline/qa_evidence.py:124-126` (`logger.info("qa_evidence.written", ...)`).
- Gate capability manifest include timestamp e scrive file in logs/:
  - `src/ui/gating.py:172-199` (campo `computed_at`) + `write_gate_capability_manifest`.
