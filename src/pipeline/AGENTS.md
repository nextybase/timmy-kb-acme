# Scopo
Area pipeline core con focus su I/O sicuro e idempotente.

# Regole (override)
- Path-safety obbligatoria: tutte le write/copy/rm passano da `ensure_within*` (no join manuali).
- Scritture atomiche tramite `safe_write_text/bytes`.
- Logging strutturato con redazione attiva (`LOG_REDACTION`) quando disponibile.

# Criteri di accettazione
- Nessuna scrittura fuori dal workspace cliente.
- Operazioni ripetibili senza corrompere stato.

# Riferimenti
- docs/AGENTS_INDEX.md
