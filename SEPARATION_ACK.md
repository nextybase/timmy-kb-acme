# Separation Acknowledgement (User/Dev split) — 1.0 Beta

## WHY
The architecture SSoT (.codex/USER_DEV_SEPARATION.md) explicitly requires that UI code does **not** import internal Drive modules (`pipeline.drive.*`) and uses the public Drive facade `pipeline.drive_utils` instead.
The guardrail test `tests/architecture/test_facade_imports.py` was inconsistent with the SSoT because it blacklisted `pipeline.drive_utils`, making compliance impossible when UI legitimately consumes the approved facade.

This change aligns enforcement with the documented 1.0 Beta import boundaries.

## IMPACT
- `pipeline.drive_utils` is no longer treated as a forbidden internal module by `test_facade_imports_only_public_surface`.
- UI code may import the approved Drive facade while still being blocked from importing `pipeline.drive.*` internals (client/download/upload).
- No behavior change in Drive runtime; this is governance/enforcement alignment only.

## RISK
- Low functional risk: this is a test/enforcement change, not a runtime logic change.
- Architectural risk (controlled): UI is allowed to depend on `pipeline.drive_utils` until Drive access is fully centralized under `ui.services.drive_runner`. The existing UI denylist continues to forbid `pipeline.drive.*` internals, preventing leakage of non-SSoT Drive APIs.

Mitigations:
- Keep `pipeline.drive` blacklisted and keep UI forbidden prefixes for `pipeline.drive.*`.
- Follow-up work will migrate UI components to use `ui.services.drive_runner` as the single UI→Drive entrypoint.

## TESTS
- pytest -q tests/architecture/test_facade_imports.py
- (optional, recommended) pytest -q tests/architecture
