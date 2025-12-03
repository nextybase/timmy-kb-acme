# ADR-0001: SQLite come SSoT per i tag runtime
- Stato: Accepted
- Data: 2025-10-24
- Responsabili: Team Timmy-KB

## Contesto
La pipeline semantica genera e consuma tag durante l'onboarding dei documenti. In passato convivevano YAML (`semantic/tags_reviewed.yaml`) e CSV (`tags_raw.csv`), con rischio di divergenza, aggiornamenti parziali e accesso concorrente tra UI e orchestratori CLI.

## Decisione
Adottiamo **SQLite (`semantic/tags.db`) come Single Source of Truth runtime** per tag, sinonimi e metadati. YAML rimane per l'authoring umano, mentre la UI e gli orchestratori leggono/scrivono solo attraverso le API `semantic.tags_*`/`storage.tags_store`.

## Alternative considerate
- **YAML esclusivo**: semplice da versionare, ma non supporta query efficienti ne garantisce l'atomicita richiesta da UI e NLP incrementale.
- **JSON/CSV + cache in memoria**: facile da manipolare ma richiede logica custom per stati consistenti e lock.
- **Servizio esterno (es. Postgres)**: offre robustezza, ma introduce dipendenza infrastrutturale non necessaria per il deployment on-premise del cliente.

## Revisione
- Rivalutare se la mole di tag supera i limiti di SQLite o se diventa necessario sharding/multi-tenant avanzato.
- Rivalutare in caso di UI multiutente con elevata concorrenza, oppure se si decide di esporre un'API remota centralizzata.
