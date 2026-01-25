# Artifacts Policy (Core vs Service) - v1.0 Beta

## Scope & intent
Questa policy definisce cosa si intende per "artefatto" nel sistema Timmy-KB
e stabilisce regole normative su determinismo, fallback, dipendenze opzionali
e tracciabilità.

Questa policy è normativa (SSoT). In caso di conflitto con `docs/` o `system/`,
prevale questa.

## Definitions

### Artifact
Un artefatto è un output materiale prodotto da pipeline/UI/CLI (file, snapshot, indice,
ledger entry, report, ecc.) che può essere consumato da persone o processi automatici.

### Core Artifact (Epistemic Envelope output)
È un artefatto:
- richiesto o implicato dalle fasi della foundation pipeline;
- consumato da step successivi come input deterministico;
- parte della catena di evidenze (audit/lineage/ledger) o della base KB.

Esempi tipici (non esaustivi): `normalized/`, `book/README.md`, `book/SUMMARY.md`,
`semantic/tags.db`, snapshot KG, ledger/lineage.

### Service Artifact (Support / UX / Tooling)
È un artefatto:
- utile per UX, diagnostica, packaging, preview o supporto operativo;
- non è prerequisito per la pipeline deterministica;
- non deve cambiare la semantica dei core artifacts né sostituirli.

Esempi: zip log, workspace summary, cache in-memory, preview, report “di servizio”.

## Beta invariants (strict)

### 1) Core artifacts MUST be deterministic
Un core artifact deve essere riproducibile a parità di input e configurazione.
Sono vietate dipendenze "best effort" o output alternativi che cambiano formato/semantica.

### 2) No silent downgrade for core artifacts
Se un core artifact richiede una dipendenza opzionale o una capability non disponibile,
il comportamento ammesso è:
- STOP con errore tipizzato (fail-fast), e
- evento tracciato (log strutturato + ledger entry se applicabile).

È vietato sostituire automaticamente un core artifact con una variante "comunque ok"
(es. generare `.txt` al posto di `.pdf` o cambiare formato senza esplicita autorizzazione).

### 3) Service artifacts MAY be best-effort (but must not masquerade)
Per i service artifacts è ammesso best-effort o fallback, a queste condizioni:
- non altera o rimpiazza core artifacts;
- è esplicito (log strutturato) e identificabile come "SERVICE_ONLY";
- non introduce dipendenza implicita in step successivi.

### 4) Optional dependencies policy
Le dipendenze opzionali sono ammesse solo se:
- abilitate tramite capability-gating (config/extra esplicito), e
- il loro fallimento non produce "successo apparente" su core artifacts.

### 5) Time-based state and caching policy
Qualsiasi cache time-based (TTL, timestamp wall-clock) è considerata *entropia operativa*.
È ammessa solo come supporto (service behavior) se:
- non influenza decisioni, ordering o selezione degli input della pipeline;
- non viene usata come condizione per produrre o saltare core artifacts;
- è confinata a performance/UX e non modifica artefatti persistenti.

Se una cache time-based viene "prewarmata" automaticamente, deve restare
non osservabile ai fini della semantica e non può diventare requisito implicito.

## Classification rule (practical)
Quando un modulo produce un file:
- se finisce in directory della pipeline (workspace layout) o viene citato come prerequisito:
  trattalo come CORE.
- se è diagnostica, packaging, preview, export UI:
  trattalo come SERVICE.

In dubbio: CORE.

## Compliance hooks (normative expectations)
- I Gatekeepers e i micro-agent (Work Order Envelope) devono trattare come violazione
  qualsiasi produzione "alternativa" non autorizzata di core artifacts.
- Un "OK" non è valido se i core artifacts attesi non sono stati prodotti nella forma prevista.
