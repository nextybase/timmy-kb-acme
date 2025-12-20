# Purpose
Documentation-specific rules covering language, alignment with UX/flow, and consistent versioning.


# Rules (overrides)
- Prefer English fr technical narratives; Italian can remain for conversational explanations when noted in the index.
- Reflect UX/flow-relevant code changes within the same PR through documentation updates.
- Keep titles/frontmatter aligned with the current release (`v1.0 Beta`) across README and docs.
- Run `pre-commit run cspell --all-files` (or limit to `docs/...` when appropriate) and favor relative links with up-to-date snippets (e.g., Python 3.11, Streamlit 1.50.0).
- When documenting Streamlit/CLI workflows, describe the orchestrators currently in use (`pipeline.github_push_flow.*`, `tools.gen_dummy_kb.build_payload`, `ui.pages.tools_check._is_gate_error`).
- Prefer service wrappers (`semantic.*_service`, `semantic.mapping_loader`) when documenting `semantic.api`; example tests should monkeypatch the re-exported wrappers.


# Acceptance Criteria
- Clean spell-check results on `docs/` and `README.md` without ad-hoc ignores.
- Frontmatter and titles consistent with published versioning.
- Update ADR/changelog entries when documentation practices or tooling change.


# References
- system/ops/agents_index.md
- system/ops/runbook_codex.md
