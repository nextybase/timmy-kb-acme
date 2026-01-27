# 14_agent_package_contract.md
**Stato:** attivo
**Ambito:** Agency Engine - struttura e identità degli agenti
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

src/ai/<agent_id>/


È vietato:
- distribuire file di uno stesso agente in più directory
- definire agenti solo tramite configurazione o environment
- utilizzare naming impliciti o convenzioni non dichiarate

---

## 5. `agent.yaml` - Carta d’identità dell’agente

Ogni Agent Package deve contenere un file:

src/ai/<agent_id>/agent.yaml


### 5.1 Ruolo del file
`agent.yaml` è la **Single Source of Truth** per:
- identità dell’agente
- tipo di agente
- ownership
- policy sugli artefatti

In **Beta 1.0**, `agent.yaml`:
- è **normativo**
- può essere **validato**
- non è necessariamente usato dal runtime per la risoluzione

### 5.2 Obblighi
- Il file deve esistere.
- Il file deve essere semanticamente coerente con il codice.
- Se il file è assente o invalido, l’agente è **non conforme**.

---

## 6. Struttura minima obbligatoria

Ogni Agent Package deve rispettare almeno la seguente struttura:

src/ai/<agent_id>/
├── agent.yaml
├── artifacts/
│ ├── latest.json
│ └── builds/
│ └── <build_id>/
│ └── build_manifest.json


### 6.1 Regole
- `artifacts/` è **append-only**
- `latest.json` è l’unico file mutabile
- gli artefatti **non devono essere committati**
- nessun artefatto può essere sovrascritto

---

## 7. Artefatti di build (`build_manifest.json`)

Ogni esecuzione valida di un agente deve poter produrre
un **build_manifest** conforme.

Il `build_manifest.json`:
- è un **artefatto di provenance**
- attesta **che cosa l’agente ha fatto**
- rende il comportamento **auditabile**

Il contenuto minimo richiesto è definito dal contratto di build vigente
(versionato nello schema del manifest).

---

## 8. Separazione tra identità, runtime e dati

È obbligatoria la separazione netta tra:

| Dominio | Contenuto |
|-------|----------|
| Identità | `agent.yaml` |
| Runtime | codice Python |
| Stato | `artifacts/` |
| Dati operativi | workspace (`raw/`, `semantic/`, ecc.) |

È vietato:
- mescolare dati runtime e codice
- dedurre stato dall’assenza/presenza di file non normati
- utilizzare fallback impliciti

---

## 9. Relazione con l’Agency Engine

Questo contratto **non modifica**:
- ruoli decisionali
- Prompt Chain
- gate, verdict, HiTL
- Work Order Envelope

Il contratto **definisce solo**:
- la forma valida degli agenti
- le condizioni minime per la loro esistenza tecnica

Le regole decisionali restano definite in:
- `instructions/AGENTS.md`
- `instructions/02_prompt_chain_lifecycle.md`
- `instructions/03_gatekeepers_contracts.md`

---

## 10. Failure modes (non negoziabili)

I seguenti casi sono da considerarsi **errori di sistema**:

- agente senza `agent.yaml`
- `agent_id` ambiguo o rinominato
- artefatti sovrascritti
- fallback impliciti su path o identità
- stato dedotto senza manifest

In presenza di tali condizioni:
- l’esecuzione **deve fermarsi**
- l’errore deve essere **esplicito e tracciato**

---

## 11. Nota di chiusura (Beta 1.0)

Questo contratto è pensato per:
- ridurre entropia strutturale
- rendere gli agenti **oggetti governabili**
- preparare l’introduzione del Builder senza migrazioni distruttive

Ogni deroga a questo documento
è una **violazione dell’envelope operativo** della Beta 1.0.
