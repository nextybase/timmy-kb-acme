# Evidence Report Post Fix (QA gate core-gate + low entropy)

Data: 2026-01-25

## Repo status
- HEAD: e709d4ec3aa1c7559eda03c4801d7c1cb9371941
- Branch: main
- Dirty: yes (modified + untracked files present)

## Diffs normativi (policy/inventory)

### Core vs Service, no silent downgrade, service no implicit deps, time-based caching, QA core-gate
Source: `instructions/13_artifacts_policy.md:17-82`
```
  17: ### Core Artifact (Epistemic Envelope output)
  18: È un artefatto:
  19: - richiesto o implicato dalle fasi della foundation pipeline;
  20: - consumato da step successivi come input deterministico;
  21: - parte della catena di evidenze (audit/lineage/ledger) o della base KB.
  26: ### Service Artifact (Support / UX / Tooling)
  27: È un artefatto:
  28: - utile per UX, diagnostica, packaging, preview o supporto operativo;
  29: - non è prerequisito per la pipeline deterministica;
  30: - non deve cambiare la semantica dei core artifacts né sostituirli.
  34: ### Core-Gate Artifact (Gate prerequisite)
  35: È un artefatto:
  36: - usato come prerequisito normativo per sbloccare la produzione di core artifacts;
  37: - può vivere in `logs/`, ma è trattato come CORE ai fini dei gate;
  38: - non introduce fallback o downgrade: se manca, il gate blocca.
  42: ### 1) Core artifacts MUST be deterministic
  43: Un core artifact deve essere riproducibile a parità di input e configurazione.
  46: ### 2) No silent downgrade for core artifacts
  47: Se un core artifact richiede una dipendenza opzionale o una capability non disponibile,
  48: il comportamento ammesso è:
  49: - STOP con errore tipizzato (fail-fast), e
  50: - evento tracciato (log strutturato + ledger entry se applicabile).
  52: È vietato sostituire automaticamente un core artifact con una variante "comunque ok"
  53: (es. generare `.txt` al posto di `.pdf` o cambiare formato senza esplicita autorizzazione).
  55: ### 3) Service artifacts MAY be best-effort (but must not masquerade)
  56: Per i service artifacts è ammesso best-effort o fallback, a queste condizioni:
  57: - non altera o rimpiazza core artifacts;
  58: - è esplicito (log strutturato) e identificabile come "SERVICE_ONLY";
  59: - non introduce dipendenza implicita in step successivi.
  66: ### 5) Time-based state and caching policy
  67: Qualsiasi cache time-based (TTL, timestamp wall-clock) è considerata *entropia operativa*.
  68: È ammessa solo come supporto (service behavior) se:
  69: - non influenza decisioni, ordering o selezione degli input della pipeline;
  70: - non viene usata come condizione per produrre o saltare core artifacts;
  71: - è confinata a performance/UX e non modifica artefatti persistenti.
  76: ### 6) QA evidence è CORE-GATE (README/SUMMARY)
  77: `logs/qa_passed.json` è un **core-gate artifact**: è prerequisito normativo
  78: per generare i core artifacts `book/README.md` e `book/SUMMARY.md`.
  81: Il campo `timestamp` può esistere come telemetria, ma **non** deve entrare
  82: nel confronto deterministico/manifest dei core artifacts.
```

### Inventory: qa_passed.json classification (CORE-GATE)
Source: `instructions/13_artifacts_policy.md:180-186`
```
 180: ### A.7 Log, diagnostica, stato UI
 185: | `src/pipeline/qa_evidence.py:write_qa_evidence` | `output/timmy-kb-<slug>/logs/qa_passed.json` | JSON QA | QA gate → README/SUMMARY | CORE-GATE | JSON serialization | No |
```

### Phase appendix: QA core-gate prerequisite for README/SUMMARY
Source: `instructions/13_artifacts_policy.md:206-212`
```
 206: ## Appendice B - CORE artifacts attesi per fase
 212: | semantic_onboarding | `output/timmy-kb-<slug>/book/<rel>.md`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | Enrichment richiede `semantic/tags.db` presente e valido. `logs/qa_passed.json` è prerequisito CORE-GATE per README/SUMMARY. |
```

### Gate checklist and contract update (QA gate + stop_code)
Source: `instructions/07_gate_checklists.md:137-154`
```
 137: ## Modulo 5 - `PREVIEW_READY → COMPLETE`
 139: **Gate richiesti:**
 140: - QA Gate
 145: **Evidence anchors:**
 147: - `logs/qa_passed.json` (CORE-GATE)
 152: 2. **QA results**
 153:    QA Gate ha prodotto verdict PASS?
 154:    Se FAIL: `stop_code = QA_GATE_FAILED`
```
Source: `instructions/08_gate_evidence_and_retry_contract.md:163-172`
```
 163: ## QA Gate ↔ Stato `COMPLETE`
 165: - Il QA Gate è **necessario ma non sufficiente** per completare la pipeline.
 170: - `logs/qa_passed.json` è il **core-gate artifact** del QA Gate.
 171: - Il campo `timestamp` è telemetria: non entra nel confronto deterministico/manifest dei core artifacts.
 172: - In caso di FAIL: verdict = `BLOCK`, `stop_code = QA_GATE_FAILED`.
```

## UI/CLI: same QA gate function usage

### Core function: QA gate uses only normative fields
Source: `src/pipeline/qa_gate.py:31-69`
```
  31: def require_qa_gate_pass(log_dir: Path, *, slug: str | None = None) -> QaGateResult:
  33:     Gate QA deterministico: usa solo campi normativi (qa_status/checks_executed).
  44:         evidence = load_qa_evidence(log_dir)
  56:     qa_status = str(evidence.get("qa_status") or "").strip().lower()
  66:     return QaGateResult(
  67:         schema_version=int(evidence.get("schema_version", 0)),
  68:         qa_status=qa_status,
  69:         checks_executed=list(evidence.get("checks_executed") or []),
```

### UI path (Semantics page)
Source: `src/ui/pages/semantics.py:288-309`
```
 288:     ctx, logger, layout = _make_ctx_and_logger(slug)
 289:     qa_marker = _qa_evidence_path(layout)
 291:         logs_dir = getattr(layout, "logs_dir", None) or getattr(layout, "log_dir", None)
 294:         require_qa_gate_pass(logs_dir, slug=slug)
 299:         log_gate_event(
 301:             "qa_gate_failed",
 309:         st.error("QA Gate mancante: esegui `python -m timmy_kb.cli.qa_evidence --slug <slug>` per generare l'evidenza.")
```

### CLI path (semantic_onboarding -> run_semantic_pipeline -> write_summary_and_readme)
Source: `src/timmy_kb/cli/semantic_onboarding.py:237-243`
```
 237:                 _require_normalize_raw_gate(ledger_conn, slug=slug, layout=layout)
 238:                 repo_root_dir, _mds, touched = run_semantic_pipeline(
 239:                     ctx,
 240:                     logger,
 241:                     slug=slug,
 242:                 )
 243:                 enforce_core_artifacts("semantic_onboarding", layout=layout)
```
Source: `src/semantic/api.py:234-264`
```
 234:     convert_impl: ConvertStage = convert_fn or convert_markdown
 237:     summary_impl: SummaryStage = summary_fn or write_summary_and_readme
 264:         _wrap("write_summary_and_readme", lambda: summary_impl(context, logger, slug=slug))
```
Source: `src/semantic/frontmatter_service.py:434-440`
```
 434: def write_summary_and_readme(context: ClientContextProtocol, logger: logging.Logger, *, slug: str) -> None:
 436:     layout = WorkspaceLayout.from_context(context)  # type: ignore[arg-type]
 440:     require_qa_gate_pass(layout.log_dir, slug=slug)
```

### Artifact policy enforcement hook
Source: `src/pipeline/artifact_policy.py:196-210`
```
 196: def _require_qa_gate(layout: WorkspaceLayout, *, phase: str) -> None:
 197:     if phase.strip().lower() != "semantic_onboarding":
 198:         return
 199:     require_qa_gate_pass(layout.log_dir, slug=layout.slug)
 208:     violations: list[_ArtifactViolation] = []
 209:     _require_qa_gate(layout, phase=phase)
```

### Decision Record mapping for QA gate failures
Source: `src/timmy_kb/cli/semantic_onboarding.py:110-114`
```
 110: def _normative_verdict_for_error(exc: BaseException) -> tuple[str, str]:
 111:     if isinstance(exc, ArtifactPolicyViolation):
 112:         return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION
 113:     if isinstance(exc, QaGateViolation):
 114:         return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_QA_GATE_FAILED
```
Source: `src/storage/decision_ledger.py:56-61`
```
  56: STOP_CODE_CONFIG_ERROR: Final[str] = "CONFIG_ERROR"
  60: STOP_CODE_ARTIFACT_POLICY_VIOLATION: Final[str] = "ARTIFACT_POLICY_VIOLATION"
  61: STOP_CODE_QA_GATE_FAILED: Final[str] = "QA_GATE_FAILED"
```

## QA evidence schema: normative vs telemetry
Source: `docs/dev/QA_GATE_POLICY.md:11-19`
```
  11: ## Campi normativi vs telemetria
  13: **Normativi (usati per il gate):**
  14: - `schema_version`
  15: - `qa_status` (`pass`/`fail`)
  16: - `checks_executed` (lista non vuota)
  18: **Telemetria (non deterministica):**
  19: - `timestamp` (wall-clock; non entra nel confronto deterministico/manifest)
```
Source: `src/pipeline/qa_evidence.py:35-56`
```
  35: def build_qa_evidence_payload(
  37:     checks_executed: Sequence[str],
  38:     qa_status: str,
  39:     timestamp: str | None = None,
  48:     telemetry: dict[str, Any] = {}
  49:     ts = timestamp or datetime.now(timezone.utc).isoformat()
  51:         telemetry["timestamp"] = ts
  52:     return {
  53:         "schema_version": QA_SCHEMA_VERSION,
  54:         "qa_status": status,
  55:         "checks_executed": normalized_checks,
  56:         _TELEMETRY_KEY: telemetry,
```
Source: `src/pipeline/qa_evidence.py:85-98`
```
  85:     # Backward compatibility: accept legacy top-level timestamp without requiring it.
  86:     legacy_timestamp = payload.get("timestamp")
  87:     if isinstance(legacy_timestamp, str) and legacy_timestamp.strip() and "timestamp" not in telemetry:
  88:         telemetry["timestamp"] = legacy_timestamp
  94:     return {
  95:         "schema_version": QA_SCHEMA_VERSION,
  96:         "qa_status": qa_status,
  97:         "checks_executed": checks,
  98:         _TELEMETRY_KEY: telemetry,
```

## Proof: timestamp does not influence PASS/FAIL or golden manifest

### PASS/FAIL depends on normative fields only (qa_status, checks_executed)
Source: `src/pipeline/qa_gate.py:31-69`
```
  33:     Gate QA deterministico: usa solo campi normativi (qa_status/checks_executed).
  56:     qa_status = str(evidence.get("qa_status") or "").strip().lower()
  66:     return QaGateResult(
  67:         schema_version=int(evidence.get("schema_version", 0)),
  68:         qa_status=qa_status,
  69:         checks_executed=list(evidence.get("checks_executed") or []),
```

### Test: normative payload stable across timestamps
Source: `tests/architecture/test_qa_evidence_low_entropy.py:17-28`
```
  17: def test_normative_payload_is_deterministic_across_timestamps() -> None:
  18:     payload_a = build_qa_evidence_payload(
  19:         checks_executed=["pre-commit run --all-files", "pytest -q"],
  20:         qa_status="pass",
  21:         timestamp="2025-01-01T00:00:00Z",
  23:     payload_b = build_qa_evidence_payload(
  24:         checks_executed=["pre-commit run --all-files", "pytest -q"],
  25:         qa_status="pass",
  26:         timestamp="2025-02-01T00:00:00Z",
  28:     assert _normative(payload_a) == _normative(payload_b)
```

### Golden manifest uses deterministic fields only (no timestamp)
Source: `tests/architecture/test_determinism_low_entropy_gate.py:66-82`
```
  66: def test_golden_manifest_matches_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  68:     fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "determinism_manifest.json"
  71:     artifacts = []
  74:             "config/config.yaml": layout.config_path,
  75:             "book/README.md": layout.book_dir / "README.md",
  76:             "book/SUMMARY.md": layout.book_dir / "SUMMARY.md",
  79:         artifacts.append({"path": rel, "sha256": _sha256(path), "bytes": path.stat().st_size})
  81:     manifest = {"schema_version": 1, "artifacts": artifacts}
  82:     assert manifest == expected
```
Source: `tests/fixtures/determinism_manifest.json:1`
```
   1: {"artifacts":[{"bytes":10,"path":"book/README.md","sha256":"c78da9afd9b3979501854652b088aacb299d9e601a07efb9f476ca98c7262c59"},{"bytes":9,"path":"book/SUMMARY.md","sha256":"d472979042ac41639fc5e45fc55464aaeefa9ec20e264099ebb7ebed728e9487"},{"bytes":1748,"path":"config/config.yaml","sha256":"ecbf5c4570215f42892b56c66b200d918a7bd895da7f0bfcaf73213c0970b5b3"}],"schema_version":1}
```

## Evidence map (concern → file → implication)

| Concern | File (linee) | Snippet | Implicazione |
| --- | --- | --- | --- |
| CORE vs SERVICE, no silent downgrade, service no implicit deps | `instructions/13_artifacts_policy.md:17-59` | Core/Service definitions + no silent downgrade + SERVICE_ONLY | Policy base per strictness e stop downgrade |
| Time-based caching as entropy | `instructions/13_artifacts_policy.md:66-74` | TTL/timestamp only for service, no core dependency | Timestamp/caching non puo` influire su core |
| QA evidence core-gate + timestamp note | `instructions/13_artifacts_policy.md:76-82` | qa_passed.json prereq + timestamp not in manifest | QA evidence normative, low entropy |
| Inventory classification for qa_passed.json | `instructions/13_artifacts_policy.md:180-185` | qa_passed.json CORE-GATE | Inventory aligns with policy |
| QA gate contract + stop_code | `instructions/08_gate_evidence_and_retry_contract.md:163-172` | qa_passed.json core-gate + timestamp telemetria + stop_code | Gate contract ties QA to BLOCK |
| UI uses shared gate | `src/ui/pages/semantics.py:288-309` | require_qa_gate_pass + qa_gate_failed log | UI enforcement uses core gate |
| CLI uses shared gate via pipeline | `src/semantic/frontmatter_service.py:434-440` | require_qa_gate_pass in write_summary_and_readme | CLI path enforces same gate for README/SUMMARY |
| Artifact policy precheck | `src/pipeline/artifact_policy.py:196-210` | require_qa_gate_pass in enforce_core_artifacts | Gate enforced at artifact policy layer |
| Decision Record stop_code for QA gate | `src/timmy_kb/cli/semantic_onboarding.py:110-114` | STOP_CODE_QA_GATE_FAILED | CLI emits BLOCK with QA stop_code |
| QA evidence schema normative vs telemetry | `docs/dev/QA_GATE_POLICY.md:11-19` + `src/pipeline/qa_evidence.py:35-56` | normative fields + telemetry timestamp | Schema definition and writer behavior |
| Timestamp does not affect PASS/FAIL | `src/pipeline/qa_gate.py:31-69` + `tests/architecture/test_qa_evidence_low_entropy.py:17-28` | gate uses qa_status + normative test | Deterministic PASS/FAIL |
| Golden manifest deterministic | `tests/architecture/test_determinism_low_entropy_gate.py:66-82` + `tests/fixtures/determinism_manifest.json:1` | manifest has path/sha256/bytes only | No timestamp in golden manifest |
