# Coding Standards Timmy-KB (minimal)

- Type hints are mandatory in core modules; avoid `Any` unless clearly justified.
- Do not use `print()` in modules; rely on `pipeline.logging_utils.get_structured_logger`.
- Always validate paths with `pipeline.path_utils.ensure_within` before writing, copying, or deleting.
- Perform I/O via `pipeline.file_utils.safe_write_text/bytes` for atomic writes (no direct `open()` calls in callers).
- Keep import-time free of side effects; execute I/O only inside functions or a `main`.
- Orchestrators handle user input and exit codes; internal modules must not call `sys.exit()` or `input()`.
- Tests run with pytest, deterministic fixtures, and no network access; mock or bypass Drive/Git. Only `.md` files in `book/` are eligible for pushes (`.md.fp` files exist but remain excluded).
- Align `ruff` and `mypy` with `pyproject.toml`, respecting the defined line length and existing rules.

## Additional Policy (pre-commit)

- Runtime `assert` statements are forbidden in `src/` (tests are exempt); raise typed exceptions (`PipelineError`, `ConfigError`, ...).
  - Hook: `forbid-runtime-asserts` (`scripts/dev/forbid_runtime_asserts.py`)
- Calling `Path.write_text`/`Path.write_bytes` is forbidden in `src/`; use `safe_write_text/bytes` (atomic) after guarding with `ensure_within`.
  - Hook: `forbid-path-write-text-bytes` (`scripts/dev/forbid_path_writetext_bytes.py`)
- SSoT path safety: any write/copy/delete must invoke `ensure_within(base, target)` before the operation.

## Module API and typing

- Export only the public API using `__all__ = [...]`; keep internal helpers/Protocols prefixed with `_`.
- Prefer local `Protocol` definitions for `context` parameters when only a few attributes are required; avoid unnecessary strong dependencies.
