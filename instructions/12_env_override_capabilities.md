# 12. Env Override Capabilities (Beta 1.0)

This document defines the **SSoT** for supported runtime environment-variable overrides in Beta 1.0.
Any override **not listed here** is considered unsupported and therefore **not allowed** during operational execution.

General rules:
- overrides MUST be explicit, deterministic, and auditable;
- no implicit fallbacks: invalid values MUST trigger deterministic stop conditions;
- overrides MUST NOT replace the base configuration (config/config.yaml).

Note: credentials and secrets (e.g., `OPENAI_API_KEY`, `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`) are **not “overrides”**; they are execution prerequisites and are outside the scope of this list.

---

## A) Gating (UI capabilities)

- `DRIVE` -> `0/false/off/no` disables the Drive flows; default = services enabled.
- `VISION` -> `0/false/off/no` disables Vision provisioning; default = services enabled.
- `TAGS` -> `0/false/off/no` disables tagging/semantic flows; default = services enabled.

---

## B) Paths / Workspace

- `REPO_ROOT_DIR` -> override for the repo root. It MUST contain `.git` or `pyproject.toml`.
- `WORKSPACE_ROOT_DIR` -> override for the workspace root; it MAY include `<slug>`.
  - In strict mode (`TIMMY_BETA_STRICT=1`), the resolved value MUST point directly to `.../output/timmy-kb-<slug>`: specifying just `.../output` without the slug causes `ConfigError(code=workspace.root.invalid)` and blocks execution.

Precedence: `REPO_ROOT_DIR` takes precedence over `WORKSPACE_ROOT_DIR` when both are valid.

---

## C) Storage / Registry

- `CLIENTS_DB_PATH` -> path relative to `clients_db/` (compact alias).
- `CLIENTS_DB_DIR` / `CLIENTS_DB_FILE` -> separate overrides always relative to `clients_db/`.
