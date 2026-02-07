# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue *Keep a Changelog* e *Semantic Versioning*.

## Recent updates
- Documentata `Dummy bootstrap events & semantics` + `Context load entropy policy (Dummy)` in `system/architecture.md`, esplicitando cosa certifica `dummy_bootstrap` e il contratto `ClientContext.load`.
- Reso il log `clients_store.workspace_root_ignored` più descrittivo/strutturato (hash/length invece di path) e confermato il comportamento di registry SSoT.
- Aggiunto test contrattuale per il caricamento unico di `ClientContext.load` post-skeleton (dummy bootstrap) e cSpell/QA correlate.

TODO (pre-1.0 Beta): audit duplicazione test (post-normalizzazione)
- Avviare audit mirato sui test non-skippati con alta densità (es. area `tests/ai/`, `tests/semantic/`, `tests/retriever*`) per individuare duplicazioni reali o near-duplicazioni.
- Distinguere tra:
  - duplicazioni nocive (stesso contratto testato più volte senza valore aggiunto),
  - duplicazioni utili (stesso shape ma casi/parametri diversi),
  - duplicazioni cross-layer (stesso contratto testato in layer differenti).
- Escludere esplicitamente dall'audit i test UI sempre skippati (policy Beta 1.0) o trattarli in sezione separata.
- Definire una strategia di consolidamento (test canonico + parametrizzazione / riallocazione di livello) evitando over-engineering.


TODO: realizzare completamente l'agent builder come definito in `instructions/14_agent_package_contract.md`.

TODO (pre-1.0 Beta): revisione logging/observability - creazione/gestione dashboard, standardizzare messaggi, separare log operativi/artefatti normativi e minimizzare entropia prima del rilascio finale. Non blocca i fix correnti.
