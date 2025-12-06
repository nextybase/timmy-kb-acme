# Scopo
Regole vincolanti per le pagine Streamlit in `src/ui/pages/`: aderenza a Streamlit 1.50.0, router nativo, UI import-safe e path-safe.

# Regole (override)
- Versione minima Streamlit 1.50.0 con router nativo obbligatorio (`st.Page` + `st.navigation`); nessun router custom.
- Import-safe: niente I/O o side-effect a import; `st.set_page_config` resta centralizzato nell'entrypoint.
- Routing/query: usare `st.navigation(pages).run()`, link interni con `st.page_link`, stato/slug tramite `ui.utils.route_state` e `ui.utils.slug`; gating coerente (ENTRY abilita la pagina, READY abilita preview/finitura).
- I/O path-safe: vietati `Path.rglob`/`os.walk`; usare `ensure_within_and_resolve`, `iter_pdfs_safe`, `safe_write_text` (atomico).
- Deprecazioni vietate: `st.cache`, qualsiasi `st.experimental_*`, `unsafe_allow_html`, `use_container_width`/`use_column_width`, router legacy o hack query.
- UX/layout: preferire `st.dialog` con fallback inline, evitare `with col` non supportati dagli stub, tema da `.streamlit/config.toml`, HTML tramite `st.html`.
- Logging con `get_structured_logger("ui.<pagina>")`, messaggi brevi senza PII, nessun `print()` o handler duplicato.
- Error handling: messaggi sintetici in UI, dettagli a log; orchestratori ripristinano gating/stato. Azioni admin solo in pagine dedicate e disabilitate se prerequisiti mancanti.

# Criteri di accettazione
- Router nativo presente (`st.Page`/`st.navigation`) e link interni via `st.page_link`; query/slug gestiti solo dagli helper dedicati.
- Nessuna API deprecata/vietata e guard CI `check_streamlit_deprecations` passante.
- I/O path-safe senza `rglob/os.walk`; scritture atomiche tramite utility SSoT.
- Logging con namespace `ui.*`, senza `print()`/PII; UI import-safe.
- Layout compatibile con stub (dialog fallback, nessun `with col` non supportato).

# Riferimenti
- docs/AGENTS_INDEX.md
- docs/streamlit_ui.md
