# MT-1 Report - NLP Run Options Legacy Usage Baseline

Data: 2026-02-16
Ambito: call-site interni repository (`src/`, `tests/`)

## Obiettivo
Verificare il livello di adozione del contratto typed-only per `run_nlp_to_db`
prima dello switch definitivo.

## Evidenza raccolta
1. Mappatura call-site interni con `rg` su `run_nlp_to_db(`.
2. Verifica assenza di parametri legacy nei call-site:
- `rebuild`
- `only_missing`
- `max_workers`
- `worker_batch_size`
- `enable_entities`

Esito baseline:
- Nessun call-site interno attivo richiede parametri legacy.
- I call-site interni usano il contratto typed (`options=...`) o la forma base senza parametri legacy.

## Decisione
Go per switch typed-only (T2) nel codice interno.

## Rischio residuo
Possibili integrazioni esterne al repository che usano ancora parametri legacy.
Mitigazione: release notes e changelog con breaking change esplicita.
