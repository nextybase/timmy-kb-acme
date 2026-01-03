# Documentazione Timmy-KB

Questa cartella contiene **documentazione pensata prima di tutto per esseri umani**: serve a orientarsi, capire come usare e come contribuire a Timmy‑KB, ed è strutturata per essere leggibile anche da agenti e strumenti automatici (in particolare ADR e documenti di contesto).

> **Nota importante**
> I file in `docs/` sono **esplicativi e descrittivi**, non normativi.
> Le regole vincolanti e la governance formale vivono in `MANIFEST.md` e in `instructions/*`; `docs/policies/*` contiene regole derivate/applicative e resta subordinato a quelle fonti.

L’organizzazione della documentazione riflette lo stesso principio adottato dal sistema:
**separare contesto, regole e operatività** per ridurre ambiguità ed entropia.

---

## Struttura della documentazione

### `docs/`
È il punto di ingresso.
Qui trovi solo documenti di orientamento rapido:
- questo `README`,
- gli *quickstart* per utenti e sviluppatori,
- l’indice generale della documentazione.

Nessuna regola vive qui: serve per capire **da dove partire**.

---

### `docs/user/`
Documentazione per **chi usa Timmy‑KB**.

Contiene guide operative e descrittive:
- uso della UI,
- flussi principali (es. arricchimento semantico),
- cosa succede durante le operazioni più comuni.

Questi file descrivono **comportamenti osservabili del sistema**, non policy o vincoli.

---

### `docs/developer/`
Documentazione per **chi sviluppa o mantiene Timmy‑KB**.

Include:
- guide tecniche,
- note di implementazione,
- review e mappe di evoluzione della pipeline,
- indicazioni su strumenti e struttura del codice.

Qui si spiega **come funziona il sistema e come evolve**, senza definire regole normative.

---

### `docs/policies/`
Documentazione **derivata/applicativa** (vincolante solo come applicazione delle regole in `MANIFEST.md` e `instructions/*`).

Questa cartella raccoglie le policy operative che tutti devono rispettare:
- regole di sviluppo,
- versioning,
- sicurezza,
- contratti di import/export,
- regole comuni per gli assistant.

Se un comportamento viola un file in `policies/`, è da considerarsi un errore nel perimetro applicativo, senza sovrascrivere `MANIFEST.md` o `instructions/*`.

---

### `docs/context/`
Documentazione di **contesto e allineamento concettuale**.

Qui vivono documenti che:
- collegano Timmy‑KB al framework NeXT,
- chiariscono cosa è implementato e cosa no,
- definiscono i boundary concettuali del progetto.

Questi file non sono guide né policy: servono a **capire il perimetro e il senso del sistema**, soprattutto in fase di review, audit o onboarding avanzato.

---

### `docs/adr/`
Architecture Decision Records.

Raccolgono le decisioni architetturali prese nel tempo, con contesto e motivazioni.

Sono documenti **scritti per esseri umani**, ma **pensati anche per essere letti e interpretati dagli agenti** come fonte di contesto decisionale: spiegano *perché* una scelta è stata fatta, non introducono nuove regole operative.

---

## Come leggere la documentazione

Un percorso consigliato:
1. `docs/README.md` e `docs/index.md` per orientarti.
2. `user/` o `developer/` a seconda del tuo ruolo.
3. `policies/` se devi verificare regole e vincoli.
4. `context/` se devi valutare allineamento concettuale, limiti e responsabilità.

Questa separazione è intenzionale: evita sovrapposizioni, riduce interpretazioni errate e mantiene la documentazione coerente con l’architettura del sistema.
