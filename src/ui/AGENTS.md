# Purpose
Rules for the Streamlit onboarding UI that prioritize correct gating and safe I/O.


# Rules (overrides)
- Follow `docs/developer/streamlit_ui.md` for routing, state management, I/O, and logging; the flow should cover configuration → Drive (provisioning + README + RAW download) → Semantics (convert/enrich → README/SUMMARY → Preview).
- Gate the Semantica tab so it is enabled only when `raw/` is present locally.
- Use native routing with `st.Page`, `st.navigation`, and helpers such as `ui.utils.route_state`/`ui.utils.slug`; avoid non-idempotent side effects.
- Enforce path-safe I/O with `ensure_within_and_resolve`, `safe_write_text`/`safe_write_bytes`, and `iter_safe_pdfs` (no unexpected `os.walk`).
- Keep user-facing messages concise while logging structured context (`ui.<page>` with slug, relative path, outcome).


# Acceptance Criteria
- Never trigger Semantica actions if `raw/` is empty or missing.
- Provide clear progress/feedback for Drive provisioning and conversion steps.


# References
- system/ops/agents_index.md
- docs/developer/streamlit_ui.md
