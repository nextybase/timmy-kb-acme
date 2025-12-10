# Purpose
Pipeline core guidance focused on secure, idempotent I/O and consistent instrumentation.


# Rules (overrides)
- Path safety is mandatory: all writes/copies/deletes must travel through `ensure_within*` instead of manual joins.
- Enforce atomic writes via `safe_write_text`/`safe_write_bytes`.
- Structured logging with active redaction (`LOG_REDACTION`) whenever the facility exists.


# Acceptance Criteria
- No write or delete happens outside the customer workspace.
- Operations remain repeatable without corrupting state.


# References
- docs/AGENTS_INDEX.md
