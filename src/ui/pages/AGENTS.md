# Purpose
Binding rules for the Streamlit page modules under `src/ui/pages/`: enforce Streamlit 1.50.0, native routing, import-safe code, and path safety.


# Rules (overrides)
- Require Streamlit 1.50.0+ with native routing (`st.Page` + `st.navigation`); custom routers are disallowed.
- Keep imports safe: no I/O or side effects during import; centralize `st.set_page_config` within the entrypoint.
- Handle routing/query with `st.navigation(pages).run()`, internal links through `st.page_link`, and state/slug via `ui.utils.route_state` and `ui.utils.slug`; gating should align with UI status (ENTRY unlocks the page, READY unlocks preview/final steps).
- Enforce path-safe I/O: forbid `Path.rglob`/`os.walk`; rely on `ensure_within_and_resolve`, `iter_pdfs_safe`, and `safe_write_text` for atomic writes.
- Ban deprecated APIs: `st.cache`, any `st.experimental_*`, `unsafe_allow_html`, `use_container_width`, `use_column_width`, and legacy routers or query hacks.
- Favor `st.dialog` with inline fallback when needed; avoid unsupported `with col` blocks during stub testing; centrally manage theme via `.streamlit/config.toml`; use `st.html` for safe HTML.
- Log through `get_structured_logger("ui.<page>")`, limit messages to short entries without PII, and avoid `print()` or duplicate handlers.
- Handle errors by showing concise UI messages and logging details; orchestrators must restore gating/state. Admin actions occur only on dedicated pages and remain disabled when prerequisites are missing.


# Acceptance Criteria
- Native routing (`st.Page`/`st.navigation`) is present with internal links handled by `st.page_link`; queries/slugs rely solely on dedicated helpers.
- No forbidden/deprecated APIs and the `check_streamlit_deprecations` guard passes.
- Path-safe I/O without `rglob/os.walk`; atomic writes through SSoT utilities.
- Logging uses the `ui.*` namespace, excludes `print()`/PII, and keeps the UI import-safe.
- Layout supports stubs (dialog fallback, no unsupported `with col` blocks).


# References
- system/ops/agents_index.md
- docs/developer/streamlit_ui.md
