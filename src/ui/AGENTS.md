# AGENT - Onboarding UI (Streamlit)
> Nota: policy comuni in `docs/AGENTS_INDEX.md`; questo file contiene solo override specifici.

## Flusso vincolante
1) Configurazione (mapping) -> 2) Drive (provisioning + README + **download RAW**) -> 3) Semantica (convert/enrich -> README/SUMMARY -> Preview).

## Regole
- Riferimento operativo: segui le linee guida di `docs/streamlit_ui.md` (router, stato, I/O, logging).
- Gating: la tab **Semantica** si abilita **solo** quando `raw/` locale e presente.
- Evita side-effects non idempotenti; persistenza solo via util SSoT (no write manuali).
- Messaggi d'errore brevi per l'utente, dettagli nei log.
- Router obbligatorio: usa `st.Page` + `st.navigation` e gli helper `ui.utils.route_state`/`ui.utils.slug` per deep-link coerenti.
- I/O path-safe: `ensure_within_and_resolve`, `safe_write_text/bytes`, `iter_safe_pdfs` (deroghe documentate), nessun `os.walk` fuori dai casi codificati.
- Logging strutturato: namespace `ui.<pagina>` con payload minimo (slug, path relativo, esito).

## Accettazione
- Nessuna azione "Semantica" se RAW vuoto.
- Progress/feedback utente chiaro su Drive e Conversione.
