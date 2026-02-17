# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue *Keep a Changelog* e *Semantic Versioning*.

**TODO** (pre-1.0 Beta):
- Limitare **God functions** in orchestratori CLI (`tag_onboarding_main`, `run_nlp_to_db`, `pre_onboarding_main`) con responsabilità multiple (I/O, gate, telemetry, ledger, business rules) -> manutenibilità e testabilità ridotte.
- Verificare **API con molti parametri** (`run_nlp_to_db`) e mix di primitive + options object -> contratto poco simmetrico.
- Hotspot tecnici
 - Funzioni >150 LOC in pipeline/cli/semantic: rischio regressioni e complessità ciclomatica elevata.
 - Loop e scansioni file/DB in onboarding e embedding richiedono profiling su workspace grandi.
 - Allocazioni string/json/logging in path ad alta frequenza da monitorare (soprattutto UI/logging).


**TODO** (pre-1.0 Beta): realizzare completamente l'agent builder come definito in `instructions/14_agent_package_contract.md`.

**TODO** (pre-1.0 Beta): revisione logging/observability - creazione/gestione dashboard, standardizzare messaggi, separare log operativi/artefatti normativi e minimizzare entropia prima del rilascio finale. Non blocca i fix correnti.
