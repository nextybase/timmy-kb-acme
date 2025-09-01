# AGENT — Onboarding UI (Streamlit)

## Flusso vincolante
1) Configurazione (mapping) → 2) Drive (provisioning + README + **download RAW**) → 3) Semantica (convert/enrich → README/SUMMARY → Preview).

## Regole
- Gating: la tab **Semantica** si abilita **solo** quando `raw/` locale è presente.
- Evita side‑effects non idempotenti; persistenza solo via util SSoT (no write manuali).
- Messaggi d’errore brevi per l’utente, dettagli nei log.

## Accettazione
- Nessuna azione “Semantica” se RAW vuoto.
- Progress/feedback utente chiaro su Drive e Conversione.
