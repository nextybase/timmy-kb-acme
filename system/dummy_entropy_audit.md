# Dummy entropy audit

## 1. Call-site inventory

| Call / path | Trigger | Purpose | Stage |
|-------------|---------|---------|-------|
| `ClientContext.load(... stage=_CTX_STAGE_POST_SKELETON)` (`tools/dummy/orchestrator.py`, post workspace creation) | Always | bootstrap precheck (vision strict), config merge, ledger attribution and logger identity | `_CTX_STAGE_POST_SKELETON` |
| `_record_dummy_bootstrap_event(..., ctx=ctx_post_skeleton)` → `_resolve_workspace_layout(..., ctx=ctx_post_skeleton)` | Always | ledger entry for `dummy_bootstrap` without reloading `ClientContext` | uses the single post-skeleton context if available |
| `_audit_non_strict_step(... ctx=getattr(logger, "_ctx_post_skeleton", None))` → `_resolve_workspace_layout` | non-strict steps (`vision_enrichment`) | ledger event for non-strict audit, reuses same context | no additional load |
| Semantic flow (`if semantic_active`) | `with_run_id/run_stage` uses the already-loaded context (`ctx_post_skeleton.with_run_id(...)`) to create `semantic_ctx`; there is no new `ClientContext.load` | headphones for Markdown conversion, QA evidence | `with_stage("dummy.semantic")` |

## 2. Flag coverage vs. entropy

- `enable_semantic=True` (vision flag optional): still only one `ClientContext.load`, errors before semantics now re-raise the original loader exception via `ctx_post_skeleton_exc`.
- `enable_drive=True`: drive helpers are stubbed in contract tests and do not trigger any additional load paths beyond the singleton context.
- `enable_vision=True`: vision steps run through the provided `run_vision_with_timeout_fn`; `ClientContext.load` remains the single post-skeleton load because `_resolve_workspace_layout` is given the existing context and semantic helper reuses it with `with_run_id`.

## 3. Contractual validation

- Added `_assert_single_context_load` helper in `tests/tools/test_dummy_bootstrap.py` to wrap `build_dummy_payload` and count the stage arguments captured by the patched `PipelineClientContext.load`.
- `test_dummy_bootstrap_loads_context_exactly_once` still checks the minimal configuration.
- `test_dummy_bootstrap_context_single_load_across_features` parametrizes three realistic feature sets (`semantic`, `drive`, `vision`) and confirms each run still yields exactly one load whose `stage` is `_CTX_STAGE_POST_SKELETON`.
