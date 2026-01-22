# NeXT ↔ Timmy-KB: Mapping concettuale

Questo documento descrive l'allineamento concettuale tra Timmy-KB,
il Manifesto e la documentazione di sistema.

L'allineamento si fonda su due **domini epistemici distinti e non sovrapponibili**:

- **Epistemic Envelope**
- **Agency Engine**

Questi domini rappresentano il riferimento canonico
per l'interpretazione dell'architettura, dei processi e delle policy.

---

## Mappa dei domini epistemici

**Epistemic Envelope**
- pipeline di ingestione e trasformazione
- artefatti strutturati (markdown, metadata)
- Knowledge Graph
- lineage, ledger e tracciabilità

**Agency Engine**
- Prompt Chain
- ruoli degli agenti (Timmy, Gatekeeper, micro-agenti)
- gate epistemici (Evidence Gate, Skeptic Gate)
- work orders e output deliberativi

## 1. Introduzione
Questo documento esplicita come i concetti chiave del framework NeXT siano tradotti operativamente in Timmy-KB. L'obiettivo è fornire ai reviewer e ai developer una bussola concettuale: il paper NeXT definisce il perimetro teorico (envelope epistemico, Human-in-the-Loop, governance by design), Timmy-KB ne rappresenta l'implementazione concreta nei file README, MANIFEST e nelle guide. Non si tratta di ripetere il manifesto, ma di mostrare dove, nel repo, ciascun asse teorico trova una corrispondenza pratica e verificabile.

## 2. Envelope epistemico
NeXT descrive un perimetro attivo di validità per gli output, con soglie di confidenza, stop e segnalazioni di fuori envelope. In Timmy-KB questo concetto è incarnato da MANIFEST.md §2 ("Il principio fondante: l'envelope epistemico") e anche dai paragrafi di README e docs/index che parlano della pipeline come fondazione che si ferma se l'envelope è superato. Lo scopo operativo è ricordare che ogni inference deve dichiarare il proprio contesto e che i meccanismi di stop proteggono la responsabilità umana.

## 3. Human-in-the-Loop e astensione
NeXT sostiene che l'essere umano resta sempre nella catena, con la possibilità di sospendere l'AI quando i segnali sono incerti. Timmy-KB riflette questa scelta nei log e nella narrativa (MANIFEST.md §3 sul HiTL e README "From Foundation Pipeline to Agency") e nelle operator experience descritte in docs/user/user_guide.md. In pratica i workflow evitano deliverable automatici: se c'è ambiguità, il sistema Astiene, registra il motivo e chiede supervisione.

## 4. Governance by design
NeXT parla di governance incorporata nei ruoli e nei contratti, non affidata a policy esterne. Timmy-KB esprime questa visione tramite instructions/* (sottolineato in MANIFEST.md §5 e README "Prompt Chain") e attraverso runbook/system/* che osservano la distinzione WHAT vs HOW. L'implementazione prevede SSoT chiari (instructions/AGENTS, system/ops/agents_index) che regolano cosa è consentito prima di ogni esecuzione.

## 5. Humility algoritmica e probabilismo
NeXT privilegia la probabilità e la consapevolezza degli errori, non la certezza assoluta. Nei testi Timmy-KB risulta umile: MANIFEST.md §§3 e 6 descrivono come l'astensione sia una funzione epistemica e "l'errore come informazione". Lo sviluppo segue questa linea: log strutturati (docs/developer/coding_rule.md) tracciano confidenza e fallback, gli strumenti di monitoraggio segnalano quando un'azione è fuori parametri.

## 6. Intelligenza civica operativa e contesto PMI
NeXT posiziona il modello come supporto per comunità reali e PMI, non ambienti ideali. Timmy-KB riprende questo focus in MANIFEST.md §§7-8 ("un sistema per contesti reali", "intelligenza civica operativa") e nelle sezioni README "From Foundation Pipeline to Agency" e docs/index che segnalano la destinazione d'uso del tool. L'obiettivo operativo è scegliere chiarezza, tracciabilità e responsabilità piuttosto che automazione totale.

## 7. Cornice teorica vs implementazione operativa
NeXT distingue il "perché" teorico dal "come" tecnico, costruendo un ponte fra principi e strumenti. Timmy-KB mette in pratica questo schema: docs/index introduce cosa fa il repository, README spiega come la pipeline abilita il passaggio a Timmy e MANIFEST.md riassume il "perché". L'intento corrente è dare al lettore mappe snelle che collegano teoria e codice, senza duplicare il manifesto.

## 8. Nota sul posizionamento del documento
Questo testo vive nell'area docs come documento di allineamento: non sostituisce MANIFEST.md ma guida chi arriva da fuori a vedere i paragoni NeXT ↔ Timmy-KB prima di esplorare README, system/ e instructions/. È un ponte concettuale utile durante le review e i controlli di compliance.
