# Purpose
UI surface for inspecting an OpenAI assistant (system prompt + raw output) and managing controlled configuration tweaks.


# Rules (overrides)
- Force read-only assistant details (id, model, system prompt) with copy/export actions; dry-run outputs are raw and the review of configurable fields requires explicit confirmation before remote writes.
- Expose proposed assistant changes as HiTL micro-PRs with clear motivation and annotated diffs.
- Path safety governs every read/write via SSoT utilities (`ensure_within*`, `safe_write_text/bytes`) and writes only within the customer perimeter.
- Operational mode prefers the Agent scenario; Full Access is allowed only for explicit tasks on dedicated branches.
- Structured logging includes `extra` context (e.g., `slug`, `file_path`, `scope`) and avoids import-time side effects.


# Acceptance Criteria
- The System Prompt modal displays `assistant_id`, `model`, full instructions, and a copy button; dry-run output remains unaltered.
- Local writes are atomic and confined to the workspace; nothing escapes the perimeter.
- Remote assistant modifications require explicit confirmation and remain proposals/micro-PRs until approved.


# References
- docs/AGENTS_INDEX.md
