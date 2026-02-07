# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue *Keep a Changelog* e *Semantic Versioning*.

## TODO (interventi in sospeso rispetto al piano)

### TODO-B — 'workspace_root_ignored' come log intenzionale
- Rendere il messaggio **esplicativo e non allarmante** (repo root come SSoT del registry; workspace root ignorato per design).
- Aggiungere nel log quali env/valori sono stati visti (senza path non deterministici, se necessario).
- Aggiornare la doc: chiarire che l’override di `WORKSPACE_ROOT_DIR` non influenza il registry.

### TODO-A — Semantica formale di `dummy_bootstrap`
- Aggiungere `stage` nel payload dell’evento (`"skeleton"` consigliato) oppure emettere due eventi distinti (`dummy_bootstrap_skeleton`, `dummy_bootstrap_complete`).
- Aggiornare doc: definizione ufficiale di cosa certifica l’evento (e cosa non certifica).
- Test: verificare che `dummy_bootstrap.stage` sia presente e stabile nel ledger.

### TODO-D — Riduzione entropia sui reload di context (solo doc/telemetria)
- Documentare le ragioni dei multipli `ClientContext.load` nelle fasi dummy (precheck / semantic / drive).
- (Opzionale) aggiungere un campo `phase` nei log `context.*` o nei call-site, senza cambiare flusso.
- Checklist audit: distinguere reload 'intenzionali' vs 'ridondanti'.

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
