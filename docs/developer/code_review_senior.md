# Code Review Senior — Contratto di revisione
**Scopo:** garantire che ogni modifica alle istruzioni, ai documenti SSoT e ai moduli di gate venga commentata, tracciata e validata secondo i gate della Prompt Chain.

## Purpose
- Spiegare perché la figura senior esiste: assicura coerenza tra gate, evidenze e state machine prima che l’Engineering Gatekeeper dichiari PASS o BLOCK.

## Review Scope
- Revisione doc-only e contrattuale: focus sulle specifiche (`instructions/*`), documentazione di supporto (`docs/*`, `system/specs/*`) e registri di gate/QA.
- Non coinvolgere codice eseguibile se non già allineato agli SSoT, e non entrare nel dettaglio dell’implementazione (per quello ci sono i flussi Codex).
- L’attenzione è sulla governance (gate, evidence, retry, QA), non sulle UI copy o testi minori.

## Checklist per il Reviewer
1. **Artefatti / gate:** i riferimenti a Evidence Gate / Skeptic Gate / QA Gate sono coerenti con instructions/05-08?
2. **State visibility:** le transizioni (`bootstrap`, `raw_ready`, `tagging_ready`, `pronto`, `arricchito`, `finito`) hanno predicate chiari?
3. **Scope safety:** ogni cambiamento documenta i path (`raw/`, `semantic/`, `book/`, `config/`) e l’OCP-plane?
4. **Observability:** vengono citati log/signals (`ui.semantics.gating_allowed`, `context.step.status`, ecc.) per confermare i passaggi?
5. **Evidence:** i gate specificano artefatti o log “PASS” o li marcano come “non formalizzato”?
6. **Retry policy:** la strategia di retry/resume è esplicitata o indicata come gap in instructions/08?
7. **QA linkage:** è chiaro che `pytest`/`pre-commit` sono prerequisiti per `finito` e/o merge?
8. **Decision record:** la segnalazione finale menziona PASS/PASS WITH CONDITIONS/BLOCK e le evidenze collegate?

## Evidence required for PASS / PASS WITH CONDITIONS / BLOCK
- **PASS:** evidenze complete (log + artefatti + checklist check) e nessun gap residuo; si annotano `pre-commit` + `pytest` log e `context.step.status`.
- **PASS WITH CONDITIONS:** alcune evidenze (es. derived state) sono “non formalizzato” ma si forniscono workaround e trace log; si documentano condizioni e responsabile.
- **BLOCK:** mancanza di artefatti (`raw/` vuoto, `tags.db` mancante) o `phase_failed`; richiede decisione HiTL con azione correttiva e aggiornamento delle istruzioni.

## Come registrare la decisione
- Annotare il risultato nel report (PASS/PASS WITH CONDITIONS/BLOCK) con riferimento ai file modificati, log contestuali e link a instructions/07 per la checklist usata.
- Menzionare l’Engineering Gatekeeper via OCP-plane come attore che ha provato il gate e indicare eventuali follow-up richiesti.
