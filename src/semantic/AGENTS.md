# Purpose
Govern semantic workflows (enrichment/frontmatter) while preserving the SSoT and idempotent behavior.


# Rules (overrides)
- Use the public `semantic.api` facade; avoid imports or invocations of `_private` helpers.
- Treat `semantic/tags.db` as the runtime SSoT; reserve `tags_reviewed.yaml` for manual authoring or migration checkpoints.
- Generate README/SUMMARY through repository utilities with idempotent fallbacks that avoid destructive overwrites.
- Ensure no import-time side effects; prefer pure functions wherever feasible.


# Acceptance Criteria
- Enrichment must not duplicate tags, must honor synonyms/aliases, and must leave non-frontmatter content untouched.
- If `tags.db` is missing, propose a safe regeneration/migration instead of silently falling back.


# References
- docs/AGENTS_INDEX.md
