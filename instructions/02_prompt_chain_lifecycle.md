Agency & Orchestration Model - v1.0 - Prompt Chain Lifecycle

## Scopo e perimetro
- Il presente documento descrive la timeline delle fasi della Prompt Chain, vista narrativa lineare.
- La state machine formale e le transizioni precise verranno definite in un documento successivo.
- Timeline e state machine sono complementari: la timeline illustra chi fa cosa e quando; la state machine specifica gli stati formali e le transizioni consentite.

## Fasi canoniche della Prompt Chain (Timeline)

### PLANNING
- **Obiettivo:** raccogliere intenti utente e identificare Domain Gatekeepers rilevanti.
- **Output richiesto:** plan operativo con intenti registrati, coverage Gatekeeper, HiTL impliciti annotati.
- **Azioni consentite:** analisi policy, consultazione AGENTS, definizione REGISTER_INTENT/REGISTER_ACTION preliminari.
- **Azioni vietate:** esecuzioni dirette, bypass di HiTL, assegnazione/invocazione di micro-agent.
- **Attori coinvolti:** Timmy/ProtoTimmy (decide); Domain Gatekeepers (consigliano vincoli, condizionano coverage e segnalano limiti)-micro-agent non partecipa.

### MICRO_PLANNING
- **Obiettivo:** dettagliare sotto-prompts e selezionare micro-agent per ogni Action registrata.
- **Output richiesto:** ordine di micro-task (Work Order Envelope) e template Action con family validata.
- **Azioni consentite:** assemblaggio prompt, assegnazione micro-agent, controllo coverage Gatekeeper.
- **Azioni vietate:** esecuzioni, registrazioni nuove Action senza HiTL, modifiche fuori timeline.
- **Attori coinvolti:**
  - Timmy/ProtoTimmy (coordina e seleziona/assegna micro-agent; unico attore autorizzato a farlo).
  - Engineering Gatekeeper/OCP e altri Domain Gatekeepers (forniscono vincoli e segnalano limiti; non decidono la selezione).
- **Nota operativa:** ogni modifica all'assegnazione di micro-agent dopo questa fase richiede HiTL esplicito (es. `REGISTER_INTENT`, `REGISTER_ACTION`, `stop_code == "HITL_REQUIRED"`).

### VALIDATION
- **Obiettivo:** assicurare che prompt e Action rispettino policy e guardrail (semantic, compliance, gate).
- **Output richiesto:** validazione formale (`StructuredResult` OK) o blocco con HiTL.
- **Azioni consentite:** invocation di VALIDATE_* Actions, controllo HiTL triggers, log degli stop.
- **Azioni vietate:** GENERATE_*/EXECUTE_* prima della validazione, bypass dei gate.
- **Attori coinvolti:**
  - Domain Gatekeepers (esaminano evidenze, validano schema e guardrail e rilasciano il verdetto).
  - Engineering Gatekeeper/OCP (control plane che applica gate procedurali come Skeptic, Entrypoint e HiTL).
  - Micro-agent (esegue i controlli tecnici dei VALIDATE_* sotto Work Order Envelope e restituisce `StructuredResult`; non prende decisioni).
  - Timmy/ProtoTimmy (riceve e registra il verdetto e coordina HiTL).
 - **Nota:** alcune Action GENERATE_* o EXECUTE_* precedenti possono richiedere una VALIDATION aggiuntiva; tale controllo ricade nella fase VALIDATION esistente, non avvia una nuova fase, e si completa prima di passare a QA.

### EXECUTION
- **Obiettivo:** esecuzione delle Action consentite (GENERATE_*, EXECUTE_*) con micro-agent.
- **Output richiesto:** artefatti generati o side effect documentati e `StructuredResult`.
- **Azioni consentite:** GENERATE_*, EXECUTE_* scoperte e loggate.
- **Azioni vietate:** registrazione di nuovi intent/action, esecuzioni senza registry.
- **Attori coinvolti:** micro-agent (esegue), Domain Gatekeepers (osservano), Engineering Gatekeeper/OCP (coordina control plane), Timmy (monitora).

### QA
- **Obiettivo:** verificare artefatti, log, HiTL compliance prima della chiusura.
- **Output richiesto:** report QA, eventuali riaperture o `stop_code`.
- **Azioni consentite:** VALIDATE_* su artefatti, controllo cspell/test, decisioni di ri-esposizione.
- **Azioni vietate:** nuove esecuzioni senza nuova fase, ignorare guardrail.
- **Attori coinvolti:** Domain Gatekeepers (valutano), Engineering Gatekeeper/OCP (gates), Timmy (approva), micro-agent può eseguire VALIDATE_* per QA.

### CLOSURE
- **Obiettivo:** archiviare la Prompt Chain, aggiornare evidenze e notificare l'utente.
- **Output richiesto:** summary, log closure, evidenza HiTL soddisfatta.
- **Azioni consentite:** registrazione record, comunicazione `message_for_ocp`, chiusura fase.
- **Azioni vietate:** nuove execution, cambi di coverage senza HiTL.
- **Attori coinvolti:** Timmy (chiude), Domain Gatekeepers (confermano), micro-agent non partecipa.

## Regole di linearità globale
- Avanzamento solo quando l'output richiesto della fase precedente è disponibile e validato.
- Ritorno a fasi precedenti è permesso esclusivamente tramite Action esplicita (es. `REGISTER_INTENT` aggiornato) e HiTL confermato.

## Ricorsività locale controllata
- I loop sono ammessi solo dentro la medesima fase e avvengono a livello di orchestrazione (es. Engineering Gatekeeper che ri-invoca uno o più micro-agent durante EXECUTION), senza aggiornare lo stato globale della timeline.
- I micro-agent non mantengono stato né dialogo: ogni iterazione è una nuova invocazione sotto Work Order Envelope.
- La ricorsività serve a rifinare prompt o validazioni senza cambiare fase principale.

## HiTL prefissati
- Obbligatori in: registrazioni (`REGISTER_INTENT`, `REGISTER_ACTION`), modifica coverage, `stop_code == "HITL_REQUIRED"`.
- Ogni fase elenca i trigger e il relativo stoppaggio tramite `message_for_ocp`.

## Phase-scoped Allowed Actions
- PLANNING: `REGISTER_INTENT`, `REGISTER_ACTION`.
- MICRO_PLANNING: definizione Work Order Envelope, assegnazione micro-agent.
- VALIDATION: `VALIDATE_*` (schema, guardrail).
- EXECUTION: `GENERATE_*`, `EXECUTE_*`.
- QA: `VALIDATE_*` (report, cspell), eventuali `NEED_INPUT`.
- CLOSURE: summary logging e HiTL confirmation.
- Nessuna Action fuori fase è valida.

## State Machine (Opzione B) - Tabella Transizioni
| STATE | EVENT | GUARD | ACTIONS ALLOWED | OUTPUT/ARTEFATTI | NEXT_STATE | NOTES |
| --- | --- | --- | --- | --- | --- | --- |
| PHASE_PLANNING | INTENT_REGISTERED | intent e coverage documentati, HiTL annotato, allowed_actions definiti | `REGISTER_INTENT`, `REGISTER_ACTION` preliminari | intent registry aggiornato, coverage file | PHASE_MICRO_PLANNING | `message_for_ocp` legacy registra il passaggio |
| PHASE_MICRO_PLANNING | ACTION_REGISTERED | Work Order Envelope completo, micro-agent assegnati sotto coverage | assegnazione micro-agent, definizione prompt | task list, Work Order documenti | PHASE_VALIDATION | nuove assegnazioni richiedono HiTL (`REGISTER_*` o `stop_code == "HITL_REQUIRED"`) |
| PHASE_VALIDATION | VALIDATION_OK | `VALIDATE_*` family, guardrail passati, nessuna EXECUTE/GENERATE attiva | `VALIDATE_*` sotto Work Order Envelope | `StructuredResult` OK, log | PHASE_EXECUTION | Control Plane applica gate Skeptic/Entrypoint |
| PHASE_VALIDATION | VALIDATION_FAIL | evidenze negative, stop_code/HiTL, coverage mismatch | sospensione e logging | stop_code, err log | PHASE_VALIDATION | Domain Gatekeepers rilasciano il verdetto e coordinano HiTL |
| PHASE_EXECUTION | EXECUTION_OK | `GENERATE_*`/`EXECUTE_*` registrate, instructions/ verificata | `GENERATE_*`, `EXECUTE_*` con side effect tracciati | artefatti, StructuredResult | PHASE_QA | prima di ogni prompt operativo la cartella instructions/ viene verificata |
| PHASE_EXECUTION | EXECUTION_FAIL | runtime error o guardrail violati | blocco e HiTL trigger | stop_code, evidenze | PHASE_VALIDATION | richiamo Domain Gatekeepers per nuova validazione |
| PHASE_QA | QA_OK | QA `VALIDATE_*` completati con `StructuredResult` positivo | `VALIDATE_*` QA scope | report QA, cspell log | PHASE_CLOSURE | |
| PHASE_QA | QA_FAIL | QA mismatch, HiTL richiesto | richieste `VALIDATE_*` aggiuntive | issue log | PHASE_EXECUTION | micro-agent restituisce `NEED_INPUT` |
| PHASE_CLOSURE | CLOSURE_CONFIRMED | summary e evidenze HiTL registrate | closure log, `message_for_ocp` | log finale, evidenza HiTL | PHASE_FINAL | timeline completata |
| PHASE_FINAL | HITL_REQUIRED | `stop_code == "HITL_REQUIRED"` persistente | nessuna Action nuova | report con `message_for_ocp` | PHASE_PLANNING | necessita intervento umano per ripartire |


## Walkthrough esemplificativo
- **Scenario:** produzione di documentazione sotto `instructions/`.
- **Sequenza:** MICRO_PLANNING (definizione Action GENERATE_*), EXECUTION (micro-agent genera file), QA (VALIDATE_* sul contenuto), CLOSURE (summaries).
- **Regola obbligatoria:** ogni prompt operativo verifica `instructions/` prima di agire per evitare divergence.

## Appendice - Stop & HiTL (Mini-C)
- stop_conditions:
  - HITL_REQUIRED:
      trigger: `stop_code == "HITL_REQUIRED"` o `_CODEX_HITL_KEY` impostato dopo invalidazioni.
      owner: Domain Gatekeepers (Semantic/Compliance) e Engineering Gatekeeper/OCP.
      required_human_action: supervisione HiTL con `message_for_ocp` e ack.
      resume_rule: riprende in PHASE_VALIDATION o PHASE_EXECUTION dopo conferma umana.
      resume_phase: SAME
  - SKEPTIC_GATE:
      trigger: Skeptic Gate attivato da guardrail.
      owner: Engineering Gatekeeper/OCP.
      required_human_action: ack documentato (SKEPTIC_ACK.md) e revisione.
      resume_rule: PHASE_VALIDATION con nuovi evidences.
      resume_phase: PHASE_VALIDATION
  - ENTRYPOINT_GUARD:
      trigger: Entrypoint Guard senza ack.
      owner: Engineering Gatekeeper/OCP.
      required_human_action: conferma di conformità e log.
      resume_rule: PHASE_PLANNING o PHASE_MICRO_PLANNING a seconda dell'ambito.
      resume_phase: PHASE_MICRO_PLANNING
  - TAG_APPROVAL_REQUIRED:
      trigger: revisione tag necessaria (invalid metadata).
      owner: Domain Gatekeepers (Compliance/Semantic).
      required_human_action: approvazione manuale.
      resume_rule: PHASE_VALIDATION con coverage aggiornata.
      resume_phase: PHASE_VALIDATION
  - INVALID_SEMANTIC_MAPPING:
      trigger: semantic_mapping.yaml mancante o invalido.
      owner: Semantic Gatekeeper.
      required_human_action: correggere mapping e loggare.
      resume_rule: PHASE_VALIDATION dopo `VALIDATE_MAPPING_SCHEMA`.
      resume_phase: PHASE_VALIDATION
  - CONTRACT_ERROR:
      trigger: micro-agent restituisce `CONTRACT_ERROR`.
      owner: micro-agent (esecuzione) notificato da Domain Gatekeepers.
      required_human_action: diagnosi e intervento operativo.
      resume_rule: PHASE_EXECUTION o PHASE_VALIDATION in base allo scenario.
      resume_phase: SAME

## Nota finale
- La timeline è lineare a livello globale; eventuali cicli locali non rompono la catena.
- La state machine formale e le transizioni verranno definite in un documento successivo, basandosi sulla timeline descritta sopra.
