Agency & Orchestration Model - v1.0 - Intents & Actions

## Definizioni essenziali
- **User Intent**: frammento narrativo dell'utente che descrive un bisogno da soddisfare; innesca una richiesta verso ProtoTimmy.
- **System Intent**: corrispettivo tecnico di un User Intent, documentato nel registry; diventa operativo solo quando ProtoTimmy lo registra esplicitamente tramite l'Action `REGISTER_INTENT`.
- **Azioni & Modes**: ogni Intent o Action fa riferimento a una tassonomia esterna di "modalità operative" (analysis, report, spike, ops-run, coding, ecc.); quella tassonomia è presupposta e non viene ridefinita qui.
- **Registry**: l'insieme di Intent e Action documentati in `instructions/`; il registry è dinamico solo nella misura in cui ProtoTimmy può creare nuovi System Intent e Action tramite le azioni apposite, sempre sotto governance HiTL.

## Registry & dinamismo governato
- **ProtoTimmy** è l'unico soggetto autorizzato a registrare nuovi System Intent o Action durante la fase di planning o micro-planning, come definito nel lifecycle della Prompt Chain; i Domain Gatekeepers ricevono solo ciò che già è documentato.
- **Registrazione Intent**: solo per mezzo dell'Action `REGISTER_INTENT` (modello sotto).
- **Registrazione Action**: solo per mezzo dell'Action `REGISTER_ACTION` (modello sotto).
- **Whitelist Actions**: Gatekeeper e micro-agent eseguono esclusivamente Action presenti nel registry; qualsiasi Action non documentata viene ignorata o genera `CONTRACT_ERROR`.
- **Micro-agent esegue, non decide**: gli agenti esecutivi (es. Codex) non valutano se un'Action debba esistere; eseguono solo quanto registrato e ritornano OK / NEED_INPUT / CONTRACT_ERROR.
- **HiTL per registrazioni**: ogni `REGISTER_INTENT` o `REGISTER_ACTION` richiede HiTL esplicito; la modifica della coverage dei Gatekeeper per un Intent richiede HiTL; lo stesso vale per `stop_code == "HITL_REQUIRED"`.

## Registry invariants (vincoli non negoziabili)
- Solo ProtoTimmy può compiere `REGISTER_INTENT`/`REGISTER_ACTION` durante PLANNING o MICRO_PLANNING; Domain Gatekeepers e micro-agent possono solo consumare ciò che è già registrato.
- Ogni Action non presente nel registry causa `CONTRACT_ERROR` o viene ignorata da Gatekeeper/micro-agent e blocca la catena.
- Il campo `allowed_actions` è una whitelist per Intent: senza una presenza esplicita l'Action è illegittima nel contesto.
- La famiglia (`VALIDATE_*` vs `GENERATE_*`/`EXECUTE_*`) deve essere compatibile con la fase corrente (see `02_prompt_chain_lifecycle.md`); altrimenti la catena richiede correzione tramite micro-planning.

## Coverage Domain Gatekeepers
- Ogni System Intent documentato dichiara quali Domain Gatekeepers sono **mandatory** e quali sono **advisory** per la richiesta.
- ProtoTimmy invoca esclusivamente quei Gatekeeper, senza variazioni "a caso"; i Gatekeeper advisory possono segnalare blocchi o raccomandazioni, un mandatory Gatekeeper può bloccare e ProtoTimmy orchestra globalmente rispettando i trigger HiTL espliciti; quel blocco è un verdetto di dominio che Timmy non può bypassare senza HiTL/governance.
- La coverage è un attributo del registro Intent e viene aggiornata solo tramite HiTL e `REGISTER_INTENT`.

## Action taxonomy
- Le Action appartengono alle famiglie:
  1. `VALIDATE_*` - controllo senza side effect (schema, stato, gate).
  2. `GENERATE_*` - generazione documentale/artefatti (README, rapporti).
  3. `EXECUTE_*` - side effect su workspace/pipeline (push, pipeline CLI).
- Un'Action può essere invocata solo se è registrata e la famiglia corrisponde al comportamento atteso.

## HiTL triggers
- Esigenze obbligatorie:
  - `REGISTER_INTENT` → HiTL.
  - `REGISTER_ACTION` → HiTL.
  - Modifica della coverage Gatekeeper di un Intent → HiTL.
  - Ricezione di `stop_code == "HITL_REQUIRED"` → HiTL, con blocco fino a supervisione.
- I Domain Gatekeepers segnalano i trigger HiTL tramite `message_for_ocp` (legacy field inteso come *message_for_gatekeeper*, non come canale diretto verso un particolare agente) e resettano `_CODEX_HITL_KEY` solo dopo conferma.

## Failure modes minimi (e cosa deve succedere)
- Action non registrata richiesta → `CONTRACT_ERROR` + stop immediato (nessuna esecuzione) e log, l'actor segnala NEED_INPUT.
- Action registrata ma fuori da `allowed_actions` → `CONTRACT_ERROR` + stop e segnalazione a ProtoTimmy per riallineamento.
- Mismatch fase/family (es. GENERATE_* durante VALIDATION) → stop e richiesta di correzione via micro-planning (resume_phase: SAME).
- Contrasto tra advisory (consiglio) e mandatory Gatekeeper che blocca → stop + HiTL escalation verso ProtoTimmy (scheduled need_input).
- `stop_code == "HITL_REQUIRED"` o tag approval gate → stop + richiesta conferma umana prima di proseguire.

## Template operativi

### INTENT SPEC (System Intent)

```yaml
intent_id: ""
name: ""
description: ""
intent_mode: "" # (analysis/report/spike/ops-run/coding/etc.)
preconditions:
  - ""
postconditions:
  - ""
inputs:
  - name: ""
    type: ""
outputs:
  - name: ""
    type: ""
coverage:
  mandatory_gatekeepers:
    - ""
  advisory_gatekeepers:
    - ""
allowed_actions:
  - ""
hitl_triggers:
  - REGISTER_INTENT
  - REGISTER_ACTION
  - MODIFY_COVERAGE
  - stop_code == "HITL_REQUIRED"
evidence_required:
  - log: ""
  - artifact: ""
```
Regola: nel contesto di questo Intent possono essere invocate solo le Action elencate in allowed_actions.
Vincolo: `allowed_actions` è obbligatorio e non può essere vuoto per Intent validi.

### ACTION SPEC

```yaml
action_id: ""
name: ""
family: VALIDATE_|GENERATE_|EXECUTE_
action_mode: ""
side_effects: "" # dichiarati e tracciati
executor: "" # es. Codex
steps:
  - description: ""
    command: ""
    # per family EXECUTE_* gli side_effects devono essere espliciti.
rollback_restart_notes:
  - ""
outputs:
  - OK
  - NEED_INPUT
  - CONTRACT_ERROR
stop_conditions:
  - ""
```

## Esempio completo
- **User Intent → System Intent:** l'utente richiede "aggiorna il mapping semantico".
- **Coverage Gatekeepers:**
  - mandatory: Semantic Gatekeeper.
  - advisory: Compliance Gatekeeper.
- **Sequence di Action**
  1. `VALIDATE_MAPPING_SCHEMA` (VALIDATE_*).
  2. `GENERATE_MAPPING_ARTIFACTS` (GENERATE_*).
  3. `EXECUTE_DEPLOY_MAPPING` (EXECUTE_*).
- Ogni Action è eseguita solo dopo che è presente nel registry e combacia con la family corretta; ogni passaggio fa riferimento ai template sopra e riporta OK/NEED_INPUT/CONTRACT_ERROR. La sequenza di Action è ammessa solo se compatibile con la fase corrente della Prompt Chain.

## Disclaimer
- `message_for_ocp` è un nome field legacy; concettualmente è un *message_for_gatekeeper* destinato a un Domain Gatekeeper, non a un singolo agente e non implica esecuzione automatica. Non autorizza né implica l'invocazione diretta di un agente specifico: il routing viene deciso da ProtoTimmy in base alla coverage dell'Intent.
