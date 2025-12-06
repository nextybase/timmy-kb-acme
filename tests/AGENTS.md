# Scopo
Gestione test con piramide unit -> middle/contract -> smoke E2E su dataset dummy.

# Regole (override)
- Dataset dummy generati con tool dedicati (mai dati reali).
- Nessuna dipendenza di rete: Drive/Git vanno mockati o bypassati.
- Contract test sui guard di `book/` (solo `.md`, ignorare `.md.fp`).

# Criteri di accettazione
- Build/test verdi in locale; smoke E2E su slug dummy riproducibile.

# Riferimenti
- docs/AGENTS_INDEX.md
