# AGENT — Test

## Strategia
- Piramide: unit → middle/contract → smoke E2E (dummy).
- Genera dataset dummy con tool dedicato (no dati reali).

## Regole
- Niente dipendenze di rete (Drive/Git mockati o bypass).
- Contract test su guard di `book/` (solo `.md`, `.md.fp` ignorati).

## Accettazione
- Build verde locale; smoke E2E su dummy slug riproducibile.
