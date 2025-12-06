# Scopo
Regole per l'onboarding UI Streamlit, orientate a gating corretto e I/O sicuro.

# Regole (override)
- Seguire `docs/streamlit_ui.md` per router, stato, I/O e logging; flusso: configurazione -> Drive (provisioning + README + download RAW) -> Semantica (convert/enrich -> README/SUMMARY -> Preview).
- Gating: la tab **Semantica** e attiva solo se `raw/` locale esiste.
- Router obbligatorio con `st.Page` + `st.navigation` e helper `ui.utils.route_state`/`ui.utils.slug`; evitare side-effect non idempotenti.
- I/O path-safe con `ensure_within_and_resolve`, `safe_write_text/bytes`, `iter_safe_pdfs` (nessun `os.walk` non previsto).
- Messaggi utente brevi, dettagli nei log; logging strutturato `ui.<pagina>` con contesto minimo (slug, path relativo, esito).

# Criteri di accettazione
- Nessuna azione "Semantica" se `raw/` e vuoto o mancante.
- Progress/feedback utente chiaro su Drive e conversione.

# Riferimenti
- docs/AGENTS_INDEX.md
- docs/streamlit_ui.md
