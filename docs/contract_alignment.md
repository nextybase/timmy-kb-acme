# Contract Alignment Notes

This document does not introduce new rules: it realigns the runtime description with the contracts already expressed in the MANIFEST and `instructions/` (higher-level documents prevail in case of conflict). It records only what the runtime actually does today - no creative proposals.

To keep documentation consistent with observed runtime behavior (no silent downgrades, testable contracts), we record the resolved mismatches here:

1. **`db_path` is always explicit and absolute.** `QueryParams` now documents that `db_path` cannot be `None` and must derive from `WorkspaceLayout`/`ClientContext`; `storage.kb_db._resolve_db_path` and `KbStore` enforce it strictly (no fallback to `None`, a global `kb.sqlite`, or a relative path).
2. **KB DB init fails on duplicates.** The UNIQUE index does not warn and continue; it raises `ConfigError`, forcing the DB to be rebuilt, as clarified in the inline comment after the index creation.
3. **`_load_env` exposes raw strings.** The context returns literal strings (including `CI`, `LOG_REDACTION`, etc.); any caller that needs a boolean flag is responsible for parsing.
4. **`RawTransformService` signals failures via exceptions.** The documentation now states that `FAIL` is never returned; errors raise `PipelineError`, `SKIP` covers unsupported formats, and `OK` means success.

These notes document the constraints split between code and contracts (Beta 1.0: determinism, fail-fast, no implicit fallback). Any future change affecting these guarantees must also update this note and the related inline documentation/comments.

Change discipline: every change that alters one of these guarantees MUST update this note and the associated inline documentation/comments.
