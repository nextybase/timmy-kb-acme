# Legacy/Fallback Catalog - 2026-02-14

Source scans: `reports/fallback_scan_2026-02-14.txt`
Policy SSoT: `instructions/13_artifacts_policy.md`

## Scan counts
- `legacy|shim|fallback|...`: 150 match
- `getattr|hasattr|inspect.signature`: 393 match
- `or getattr(`: 10 match
- `try:...except...TypeError` (single-line heuristic): 0 match
- `return []|{}|None`: 250 match

## Runtime triage (high signal)

| Path | Match | Class | Decision |
| --- | --- | --- | --- |
| `src/timmy_kb/cli/semantic_onboarding.py:111` | `getattr(layout, "normalized_dir", None)` in evidence refs | CORE-GATE (semantic onboarding gate evidence) | NON AMMESSO (dual-contract). Fixed: direct `layout.normalized_dir`. |
| `src/timmy_kb/cli/retriever_logging.py` | logger fallback chain | SERVICE_ONLY | Ammesso (non influenza gating/artifact core). |
| `src/timmy_kb/cli/retriever_embeddings.py` | multiple `return []` on provider/runtime errors | SERVICE_ONLY | Ammesso se resta observabile; monitorare entropy guard. |
| `src/ui/pages/logs_panel.py` | UI capability fallback (`link_button`/`button`) | SERVICE_ONLY | Ammesso (UX-only). |
| `src/semantic/book_readiness.py` | import constants fallback | SERVICE_ONLY (preview/readiness helper) | Ammesso; non impatta core artifacts. |
| `src/pipeline/content_utils.py:910` | frontmatter fallback -> raw read | CORE | Da monitorare: fallback non-silenzioso già loggato; non toccato in questo micro-PR. |
| `src/pipeline/config_utils.py:46` | `_SettingsConfigDict` shim in TYPE_CHECKING | N/A (typing only) | Non-runtime, fuori scope hardening Beta runtime. |

## Micro-PR executed in this branch
- Removed dual-contract fallback in semantic onboarding evidence refs.
- Added regression test that enforces normalized path in evidence refs.
- Updated CLI semantic onboarding test stub to provide full `WorkspaceLayout` contract (`normalized_dir`).

## Next micro-PR queue (non-ammesse/ambigue)
1. Review CORE fallback in `src/pipeline/content_utils.py` (`frontmatter_fallback`) against strict policy.
2. Scan CORE/CORE-GATE modules for `getattr(..., None)` only where attribute is mandatory by contract (`WorkspaceLayout`, `ClientContextProtocol`).
3. Add/extend architecture guardrail to fail on new dual-contract patterns in CORE paths (e.g. `getattr(layout, "...", None)` when layout field is mandatory).
