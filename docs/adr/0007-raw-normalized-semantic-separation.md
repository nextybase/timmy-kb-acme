# ADR-0007: Separazione RAW / NORMALIZED / SEMANTIC
- Stato: Accepted
- Data: 2026-01-23
- Responsabili: Timmy KB Architecture Group

## Contesto

L'uso diretto di `raw/` come input per tagging e semantica introduce entropia:
la trasformazione dei PDF evolve nel tempo, ma i passi semantici dipendono da un
formato stabile e riproducibile. Serviva una separazione esplicita tra:

- **RAW**: evidenza originale (PDF).
- **NORMALIZED**: derivato testuale deterministico.
- **SEMANTIC**: tagging, NLP, KG e arricchimenti.

## Decisione

Si adotta una separazione fisica e logica:

1. `raw/` resta l'evidenza sorgente e non viene mai letta dalla fase semantica.
2. `normalized/` diventa l'unico input per tagging, NLP, KG e conversione in `book/`.
3. `raw_ingest` normalizza i PDF e produce `normalized/INDEX.json`.
4. Il Decision Ledger registra il gate `normalize_raw`; `semantic_onboarding` richiede tale gate in modo bloccante.
5. La UI effettua il gating su `normalized/`, non su `raw/`.

## Alternative considerate

- **Continuare con `raw/` come input semantico**: scartato per rischio di regressioni e difficolta di audit.
- **Conversione on-the-fly dentro la semantica**: scartata per mancanza di isolamento e versioning del transformer.

## Revisione

Rivedere se:
- `raw_ingest` viene esposto come passo UI nativo,
- cambia il contratto del Raw Transform Service,
- emergono esigenze di versioning piu' granulari per `normalized/`.
