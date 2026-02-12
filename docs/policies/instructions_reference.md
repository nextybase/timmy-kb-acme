# Prompt Chain & Governance (derived from `instructions/*`)

> **Authority / precedence**
>
> Questo documento e **derivato**: non crea regole nuove.
> In caso di conflitto prevale: `MANIFEST.md` -> `instructions/*` -> codice -> `docs/*`.

## Perche esiste (semplicita, non burocrazia)

Le regole vere stanno in `instructions/`. In pratica pero:
chi sviluppa tende a cercare in `docs/`, e molte review tecniche falliscono
non per bug ma per ambiguita su dove sono i vincoli.

Questa policy fa due cose:
1. porta in `docs/` una mappa rapida delle regole in `instructions/*` (senza duplicare tutto);
2. evidenzia le zone a rischio entropia che sono intenzionali (e quindi non devono generare falsi positivi).

## Mappa rapida dei pilastri normativi (SSoT)

### 1) Agency-first (chi decide vs chi esegue)

Nel modello Timmy-KB la pipeline e i moduli tecnici sono HOW (strumenti):
non sono agency e non prendono decisioni di merito.
La governance (ruoli, gate, responsabilita) vive in `instructions/*`.

Per i developer: quando trovi un comportamento strano, la prima domanda non e
dove lo refactoriamo?, ma e un vincolo di governance o un bug di implementazione?

### 2) Prompt Chain e gate (ruoli, stati, criteri)

Le macchine a stati, la lifecycle della chain e i gate checklists sono normati in
`instructions/*` e fanno da contratto mentale per:
- orchestrazione OCP,
- produzione di artefatti,
- qualita delle evidenze (evidence-based),
- stop conditions.

Se in review stai discutendo cosa e accettabile, devi poter puntare a una regola
di `instructions/` (non a una preferenza di stile).

### 3) Artefatti: core vs service

La separazione core artifacts vs service artifacts esiste per ridurre entropia:
il core deve essere riproducibile e auditabile, i service servono a UX e tooling.

Il riferimento normativo resta `instructions/13_artifacts_policy.md`.

## Zone a rischio entropia (e come NON scambiarle per bug)

> Obiettivo: preservare semplicita senza introdurre overengineering difensivo.
> Se una zona di entropia e utile, deve essere confinata, osservabile e
> documentata.

### A) Cache locali (frontmatter, UI session, ecc.)

Sono accettabili solo se:
- non cambiano il risultato vero del core,
- hanno invalidazione chiara (mtime/size, reset a fine run, ecc.),
- non diventano un canale di persistenza implicita.

Esempio pratico gia normato nelle Coding Rules:
la cache del frontmatter e LRU bounded e va gestita con reset/clear nei run lunghi.

**Come documentarla per evitare falsi positivi**
- dichiarare chiaramente: e una cache service, non un artefatto core
- citare invalidazione/limiti
- agganciare un evento/log quando incide su flussi UI o benchmark

### B) Service artifacts (UI, preview, ledger non-core)

Sono i candidati piu frequenti a generare false regressions:
file e stati che esistono per UX/observability, non per determinismo del core.

Devono:
- stare nel workspace (non in repo root),
- essere chiaramente etichettati come service,
- non essere richiesti per la correttezza del core.

### C) Env overrides / capabilities

Le env var sono spesso una fonte di entropia perche cambiano comportamento tra ambienti.
La regola pratica e:
- **env core**: minimo indispensabile per risolvere workspace in modo deterministico;
- **env capability**: richieste solo se una capability e attiva (Drive, Vision, ecc.).

Per evitare falsi positivi:
- indicare sempre se una variabile e core o capability
- evitare magic fallback (se manca, fail-fast con errore esplicito)

### D) Dummy mode / tooling

E ammessa come perimetro di test controllato (smoke e2e), mai come runtime alternativo.
Se un comportamento diverge dal core, quella divergenza:
- deve essere strettamente necessaria,
- confinata in `tools/`,
- documentata e loggata,
- non deve introdurre contratti alternativi.

Questa e una delle aree piu delicate per la Beta: e facile che diventi scappatoia.

### E) Degrado controllato vs fallback

Degrado controllato ammesso solo se:
- deterministico,
- osservabile,
- disambiguabile (capisci perche e successo).

Fallback silenzioso e sempre un anti-pattern (Beta error).

## Dove trovare le regole vere (indice minimo)

Questa pagina non sostituisce `instructions/*`.
Serve solo da ponte per developer.

Riferimenti normativi principali:
- `MANIFEST.md` (principi e vincoli globali)
- `instructions/*` (agency, prompt chain, gate, contratti, artifacts policy)

Riferimenti operativi in docs:
- `docs/developer/coding_rule.md` (regole tecniche vincolanti per implementazione)
- `system/specs/promptchain_spec.md` (SSoT tecnico della spec di orchestrazione)

## Nota finale (per evitare drift)

Se aggiungi o modifichi un vincolo in `instructions/*`,
questa pagina va aggiornata solo se cambia:
- la mappa mentale per developer,
- oppure la lista delle entropy hotspots riconosciute come intenzionali.

Se la modifica e solo dettagliata/locale, non duplicarla qui: evita drift.
