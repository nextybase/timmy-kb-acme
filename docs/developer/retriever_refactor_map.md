# Retriever Refactor Map (Post-Kernel)

Status: v1.0 Beta - factual map + refactor notes
Scope: descrive lo stato attuale del retriever (confini funzionali, eventi/log, short-circuit) e annota possibili micro-step di estrazione senza cambiare semantica.

## Stato attuale (evidenza nel codice)

- **Modulo effettivo**: `src/timmy_kb/cli/retriever.py` (header: `# src/retriever.py`) funge da facade e wiring verso i sottocomponenti `retriever_*`.
- **Sottocomponenti principali**:
  - `retriever_validation` (QueryParams / contratti input)
  - `retriever_throttle` (deadline, parallelism, guard)
  - `retriever_embeddings` (embed query + normalize)
  - `retriever_ranking` (cosine, scoring/ranking deterministico)
  - `retriever_manifest` (evidence + manifest)

Nota: la dicitura "shim vs implementation" va considerata **storica** finché non esiste un file separato `src/retriever.py` nel tree.

## 1) Current functional decomposition (retriever.py)
Major responsibilities and implicit boundaries:
- Query params and validation
  - `QueryParams` dataclass, `SearchMeta/SearchResult` types, `_validate_params/_validate_params_logged`.
  - Implicit boundary: validation + error semantics (raises `RetrieverError`).
- Throttling and latency budget
  - `_ThrottleState/_ThrottleRegistry`, `_throttle_guard`, `_normalize_throttle_settings`,
    `_build_throttle_settings`, `_deadline_from_settings`, `_deadline_exceeded`.
  - Implicit boundary: concurrency control vs ranking pipeline.
- Embedding preparation
  - `_materialize_query_vector`, `is_numeric_vector/normalize_embeddings` usage.
  - Implicit boundary: embedding client interface + error handling (`retriever.query.embed_failed`).
- Candidate fetch and ranking
  - `_load_candidates`, `_coerce_candidate_vector`, `_rank_candidates`, `cosine`.
  - Implicit boundary: DB fetch (`fetch_candidates`) vs in-memory scoring.
- Metrics and observability
  - `_log_retriever_metrics`, `retriever.metrics`, `retriever.candidates.fetched`,
    `retriever.query.embedded`, `retriever.latency_budget.hit`.
  - Implicit boundary: operational logging vs core compute.
- Result assembly and evidence manifest
  - `retriever.evidence.selected`, optional manifest write (`safe_write_manifest`)
    with `retriever.response.manifest`.
  - Implicit boundary: output packaging + explainability side-effects.
- Config/budget helpers and facade
  - `with_config_candidate_limit`, `choose_limit_for_budget`,
    `with_config_or_budget`, `search_with_config`, `preview_effective_candidate_limit`.
  - Implicit boundary: config-driven policy vs raw search.

## 2) Contratto operativo osservabile (v1.0 Beta)

### Short-circuit a `[]` (non-silenzioso)
Il retriever può ritornare `[]` in condizioni diverse (input non utile, deadline/budget, embedding failure). Il valore di ritorno è uguale ma gli eventi emessi differiscono.

### Eventi principali (`retriever.*`)
Gli eventi sono parte dell'osservabilità e costituiscono l'unico disambiguatore affidabile dei casi "empty result".

## 3) Kernel touchpoints (aspirazionale / best-effort)
Where bridge fields should be present or passed (non garantito in Beta):
- Entry points: `search(...)`, `search_with_config(...)`, `retrieve_candidates(...)`.
  - Expected fields: `run_id`, `slug`, `phase_id`, `state_id`, `intent_id`, `action_id`.
- Throttle and budget warnings:
  - Events `retriever.throttle.timeout`, `retriever.throttle.deadline`,
    `retriever.latency_budget.hit`.
  - Should include `run_id/slug/phase_id/state_id` (if available) and reason/stage.
- Embedding failures:
  - Event `retriever.query.embed_failed` and `retriever.query.invalid`.
  - Stop/HiTL candidate: repeated embed failures or invalid embeddings.
- Candidate loading/ranking:
  - Events `retriever.candidates.fetched`, `retriever.metrics`.
  - Should carry `slug`, `scope`, candidate counts; add bridge fields if available.
- Evidence selection + manifest:
  - Events `retriever.evidence.selected`, `retriever.response.manifest`.
  - Should include `run_id/slug/intent_id/action_id` to tie evidence to the kernel chain.

Stop/HiTL conditions (best-effort / policy-layer):
- `RetrieverError` on invalid params (`_validate_params`): candidate for STOP with user input.
- Embedding client failure in `_materialize_query_vector`: candidate for HiTL if persistent.
- Budget exhaustion (`retriever.latency_budget.hit`) with empty results: candidate for STOP or retry gate.

Canonical gate events (BLOCK/FAIL) that could be emitted later:
- On validation failure: `evidence_gate_blocked` (missing/invalid inputs).
- On embedding failure: `qa_gate_failed` (if treated as critical quality gate).
- On budget exhaustion causing empty results: `skeptic_gate_blocked` (if policy requires).
Note: no PASS events are planned.

## 4) Risks of splitting modules
Behavioral risks:
- Changing ordering or thresholds in `_rank_candidates` can alter scores/ranking.
- Moving throttling logic can change latency behavior or semaphore timing.
- Altering embedding normalization path can change skip/score outcomes.

Test risks and preserving green suite:
- Tight coupling with logging events (`retriever.*`) may break snapshot/logging tests.
- Manifest path and content used in explainability tests must remain stable.
- Maintain deterministic ordering (`sorted` and heap behavior) to avoid flaky tests.

## 5) Proposed micro-PR sequence (C1..Cn)
1) C1: "Extract throttling helpers"
   - Scope: isolate `_ThrottleState/_ThrottleRegistry/_throttle_guard` into a helper module.
   - Tests: `python tools/test_runner.py fast -- -k "retriever"`.
2) C2: "Extract validation + params"
   - Scope: move `QueryParams` + `_validate_params` + config coercion helpers.
   - Tests: `python tools/test_runner.py fast -- -k "retriever"`.
3) C3: "Extract embedding and candidate normalization"
   - Scope: move `_materialize_query_vector` + `_coerce_candidate_vector`.
   - Tests: `python tools/test_runner.py fast -- -k "retriever"`.
4) C4: "Extract ranking + metrics"
   - Scope: move `_rank_candidates` + `_log_retriever_metrics` + `cosine`.
   - Tests: `python tools/test_runner.py fast -- -k "retriever"`.
5) C5: "Extract manifest/evidence packaging"
   - Scope: isolate manifest build and `retriever.evidence.selected` payload assembly.
   - Tests: `python tools/test_runner.py fast -- -k "explainability or retriever"`.
6) C6: "Finalize facade-only retriever module"
   - Scope: leave `search/search_with_config` as thin orchestration over extracted pieces.
   - Tests: `python tools/test_runner.py fast -- -k "retriever"`.
