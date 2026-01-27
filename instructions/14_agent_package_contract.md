# 14_agent_package_contract.md
**Stato:** attivo
**Ambito:** Agency Engine – struttura e identità degli agenti
**Autorità:** `instructions/*` (SSoT normativa)
**Precedenza:** MANIFEST.md → instructions/* → codice → docs/

---

## 1. Scopo del documento

Questo documento definisce il **contratto strutturale obbligatorio** per tutti gli agenti
(micro-agenti e gatekeeper) dell’ecosistema Timmy-KB in **Beta 1.0**.

Il contratto stabilisce:
- come un agente è **identificato**
- dove un agente **vive nel repository**
- quali **artefatti** può produrre
- quali **comportamenti sono vietati**

Se un agente, o una sua implementazione, viola una regola di questo documento,
il comportamento è da considerarsi **non ammesso** nel sistema.

---

## 2. Definizione di Agent Package

Un **Agent Package** è l’unità minima valida per rappresentare un agente nel sistema.

Un Agent Package è composto da:
- una **identità formale**
- una **struttura di repository vincolata**
- un insieme di **artefatti di runtime tracciabili**

Un agente **non esiste** nel sistema se non è rappresentato da un Agent Package conforme.

---

## 3. Identità dell’agente (SSoT)

### 3.1 `agent_id`
Ogni agente deve avere un `agent_id` che soddisfi **tutte** le condizioni seguenti:

- è **semantico e leggibile**
- è **filesystem-safe**
- è **immutabile nel tempo**
- è **globalmente unico** nel repository

Il `agent_id`:
- **non può essere rinominato**
- **non può avere alias**
- **non può essere riutilizzato**

Se il ruolo o lo scopo di un agente cambia in modo incompatibile,
deve essere creato **un nuovo agente con nuovo `agent_id`**.

---

## 4. Posizionamento nel repository (obbligatorio)

Ogni agente deve vivere **esclusivamente** nel seguente path:
