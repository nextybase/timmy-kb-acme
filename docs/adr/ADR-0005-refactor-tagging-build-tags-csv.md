# ADR-0005: Refactor tagging con build_tags_csv in semantic.tagging_service
- Stato: Accepted
- Data: 2025-12-22
- Responsabili: Team Timmy-KB / OCP / Codex Agent

## Contesto
`semantic.api` stava accumulando responsabilita implementation-heavy, con logica di dominio, scritture su filesystem, mutazioni DB e enforcement di policy dentro una facciata pubblica. `build_tags_csv` in particolare combinava orchestrazione e persistenza, rendendo meno chiari i confini architetturali tra facade/orchestration e domain/persistence.

## Decisione
- `build_tags_csv` viene spostata in un modulo dedicato `semantic.tagging_service`.
- `semantic.api.build_tags_csv` rimane esposta come delega pubblica retro-compatibile.
- Nessun cambiamento funzionale: stessi side effect, ordering invariants e schema.
- Artefatti invariati: `tags_raw.csv`, `README_TAGGING.md`, `tags.db` (doc_entities).
- Call site invariati (CLI, UI, tooling).
- Validazione tramite Prompt Chain formale: Evidence Gate superato e HiTL escalation risolta prima dell'accettazione.
- QA completa: eseguito `pytest -q` sull'intero repository.
  - Risultato: 855 passed, 10 skipped, 3 deselected.

## Alternative considerate
- Lasciare `build_tags_csv` in `semantic.api`.
- Ulteriore split compute vs persistence: esplicitamente differito, non rigettato.

## Revisione
- Rivalutare se `semantic.api` torna ad accumulare logica di dominio (o cresce il fan-in verso la facade).
- Rivalutare se il tagging richiede una separazione compute/persist piu netta.
- Rivalutare se emergono nuove invarianti d'ordine o nuovi artefatti nel flusso di tagging.
