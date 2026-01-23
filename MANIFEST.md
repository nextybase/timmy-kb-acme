# MANIFEST.md
## Timmy-KB e il paradigma dell'envelope epistemico

### 1. Perché esiste Timmy-KB
Timmy-KB nasce da una presa di posizione netta: l'intelligenza artificiale non deve sostituire il giudizio umano, né simulare una falsa oggettività, ma **costruire contesti cognitivi migliori** in cui gli esseri umani possano decidere con maggiore consapevolezza.

In un mondo dominato da modelli sempre più potenti e opachi, Timmy-KB rifiuta l'idea di un'AI onnisciente, neutra o autonoma. Accetta invece l'incertezza come dato strutturale, e la rende **visibile, tracciabile, governabile**.

Il sistema non nasce per "avere ragione", ma per **rendere esplicito ciò che è ancora aperto**.

---

### 2. Il principio fondante: l'envelope epistemico
Al centro di Timmy-KB c'è il concetto di **envelope epistemico**.

Timmy-KB è strutturato attorno a **due domini epistemici distinti e non sovrapponibili**:

- **Epistemic Envelope**
- **Agency Engine**

Entrambi utilizzano inferenza artificiale, ma sono separati dal concetto di *agency*.
Questa separazione costituisce il confine filosofico e operativo fondamentale del sistema.

L'Epistemic Envelope è il dominio dell'**inferenza senza agency**.
L'Agency Engine è il dominio dell'**inferenza con agency**.

Ogni violazione o confusione tra questi due domini costituisce un errore architetturale.

L'ownership non è un artefatto epistemico e non fa parte dell'Epistemic Envelope: è una policy di accesso del Control Plane, versionata e gestita separatamente.

Un envelope epistemico è il perimetro entro cui un sistema può operare in modo:
- semanticamente coerente
- eticamente controllabile
- operativamente verificabile

Non è un limite passivo, ma una **struttura attiva di validità**.

Timmy non decide al posto dell'umano: opera **dentro un ambiente progettato**, dove:
- il dominio è esplicitato
- le fonti sono dichiarate
- le azioni consentite sono finite
- l'incertezza ha soglie e conseguenze

Ogni inferenza, suggerimento o output è valido **solo all'interno di quell'envelope**. Fuori da esso, il sistema si ferma.

---

### 2.a Epistemic Envelope (inferenza senza agency)
L'Epistemic Envelope governa i processi di ingestione, normalizzazione, arricchimento semantico,
costruzione dei metadati e del Knowledge Graph.

In questo dominio l'inferenza è **ammessa esclusivamente in forma descrittiva e costruttiva**:
il sistema può proporre strutture e relazioni, ma non può prendere decisioni, selezionare alternative
o produrre output deliberativi.

Ogni trasformazione è:
- tracciata
- riproducibile
- reversibile
- verificabile a posteriori

L'obiettivo non è produrre risposte, ma **costruire il perimetro del conoscibile**.

### 3. Probabilismo e umiltà operativa
Timmy-KB adotta un paradigma **probabilistico nell'Agency Engine**, e
un paradigma **operativamente deterministico nell'Epistemic Envelope**.

Ogni risultato:
- ha un grado di confidenza
- può essere sospeso
- può richiedere escalation umana

L'astensione non è un errore: è una **funzione epistemica**.

Quando il contesto è ambiguo, incompleto o fuori dominio, il sistema:
- non improvvisa
- non "riempie i buchi"
- non produce certezze cosmetiche

Attiva invece meccanismi di **Human-in-the-Loop**, come definiti in `instructions/*`.

Questa postura è una scelta progettuale: **l'umiltà algoritmica è una forma di affidabilità**.

---

### 3.a Agency Engine (inferenza con agency)
L'Agency Engine è il dominio in cui l'inferenza assume carattere deliberativo.

Qui operano la Prompt Chain, i Gatekeeper e i micro-agenti.
Il sistema esplora alternative, valuta traiettorie e produce output operativi e creativi,
accettando il probabilismo e l'emergenza come strumenti progettuali.

L'Agency Engine non è deterministico nel risultato,
ma è **vincolato nel contesto**:
il suo spazio d'azione è interamente delimitato dall'Epistemic Envelope.

Nessuna decisione o output dell'Agency Engine è valido
se non è riconducibile all'envelope epistemico attivo.

### 4. Timmy non è un agente autonomo
Timmy-KB non è un soggetto decisionale.

È:
- un **orchestratore di conoscenza**
- un **amplificatore semantico**
- un **dispositivo di chiarificazione**

L'agency esercitata dal sistema è sempre **mediata, contestuale e revocabile**,
e risiede esclusivamente nell'Agency Engine.

Le decisioni restano sempre:
- attribuibili
- tracciabili
- umane

Il sistema rende più chiari i vincoli, non li crea. Rende esplicite le alternative, non le impone.

Ogni tentativo di usare Timmy come scorciatoia decisionale è un abuso del sistema.

---

### 5. Governance by design, non by policy
La governance di Timmy-KB non è demandata a linee guida esterne o controlli ex-post.

È **incorporata nell'architettura**:
- nei ruoli
- nei contratti
- nelle fasi
- nei meccanismi di stop

La cartella `instructions/` è l'unica fonte di verità normativa (SSoT). Tutto il resto - codice, documentazione, UI - **deriva** e **obbedisce**.

Questo non è un dettaglio organizzativo, ma una scelta politica: la governance non è un accessorio, è il sistema.

---

### 6. L'errore come informazione
In Timmy-KB:
- l'errore non viene nascosto
- l'incertezza non viene mascherata
- il fallimento non viene rimosso

Ogni deviazione è:
- loggata
- leggibile
- utilizzabile per apprendimento

Il sistema cresce non perché "sbaglia meno", ma perché **capisce meglio dove e perché sbaglia**.

---

Definiamo qui i principi e i limiti della conoscenza; il perimetro operativo completo, con strumenti e policy, vive altrove e può essere aggiornato mantenendo intatti i confini epistemici.

### 7. Un sistema per contesti reali
Timmy-KB non è pensato per ambienti ideali.

Nasce per:
- PMI
- team eterogenei
- contesti a bassa maturità digitale
- domini incompleti e in evoluzione

Per questo privilegia:
- chiarezza alla performance
- tracciabilità alla velocità
- responsabilità all'automazione totale

---

### 8. Posizionamento finale
Timmy-KB è uno strumento di **intelligenza civica operativa**.

Non promette risposte perfette. Promette **decisioni meglio fondate**.

Non elimina il rischio. Lo rende visibile.

Non sostituisce l'umano. Lo responsabilizza.

Questo manifesto non è una dichiarazione d'intenti astratta: è la descrizione del perimetro entro cui il sistema accetta di esistere.

Fuori da questo perimetro, Timmy-KB preferisce non parlare.

---

### 4.a Principio di cooperazione asimmetrica
L'intelligenza del sistema non risiede in uno dei due domini presi singolarmente,
ma **nella loro separazione rigorosa e nella loro cooperazione asimmetrica**.

- L'Epistemic Envelope riduce l'incertezza strutturale.
- L'Agency Engine utilizza l'incertezza residua come spazio di esplorazione controllata.

L'Epistemic Envelope precede logicamente e operativamente l'Agency Engine.

### 9. Rigor e fallimento esplicito
Timmy-KB distingue nettamente i domini di tolleranza all'errore:
- **Agency Engine (Prompt Chain / governance agentica):**
  il non-fatal è ammesso solo qui perché l'errore è cognitivo
  ed è gestito tramite Evidence Gate + Skeptic Gate.
- **Epistemic Envelope e runtime operativo:**
  le failure infrastrutturali sono **strict** o devono emettere segnali deterministici e tracciabili;
  è vietata ogni degradazione silenziosa.

Runtime behavior is governed by `instructions/10_runtime_strict_contract_beta.md`.
Questa asimmetria protegge l'envelope epistemico: l'incertezza del dialogo agentico resta osservabile e governata, mentre l'operatività pretende fallimenti espliciti e telemetria (log/eventi/exit code) che rendano verificabili cause e impatti.

---

### 10. Capabilities (Core vs Optional adapters)

La separazione tra core deterministico e integrazioni opzionali è parte della
struttura architetturale (ambienti dedicati, feature disponibili per capability).

| Capability | Ambito | Regola fail-fast |
|---|---|---|
| Core deterministico (pipeline, artefatti locali, workspace layout, gating, ledger) | Runtime core | Strict/fail-fast; nessun fallback silenzioso |
| Adapter opzionali (es. Google Drive) | Integrazioni capability-gated | Prerequisiti espliciti; assenza è un esito verificabile "feature unavailable" |

Per gli adapter opzionali:
- prerequisiti: extras `.[drive]`, `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`;
- se mancano, la capability deve fallire in modo esplicito (errore di capability), non in modo degradato;
- `--dry-run` e modalità locali sono first-class e non dipendono dalla presenza di Drive.
