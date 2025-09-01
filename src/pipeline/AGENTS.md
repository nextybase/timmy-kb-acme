# AGENT — Pipeline Core (I/O & Safety)

## Regole
- **Path‑safety**: tutte le write/copy/rm passano da `ensure_within*` (no join manuali).
- **Scritture atomiche**: `safe_write_text/bytes` obbligatorie.
- Logger strutturato se disponibile; redazione attiva in prod/LOG_REDACTION.

## Accettazione
- Nessuna write fuori dal workspace cliente.
- Operazioni ripetibili senza corrompere stato (idempotenza).
