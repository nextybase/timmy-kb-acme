# Developer Guide v1.0 Beta

> **Nota di autorità:** questo documento è narrativo e non normativo. Spiega
> razionale, onboarding e contesto. Le regole tecniche vincolanti sono in
> [Coding Rules](coding_rule.md); la mappa tecnica e le responsabilità sono in
> [Architecture Overview](../../system/architecture.md).

## Normative context

Questo progetto adotta una separazione intenzionale tra:
- documentazione tecnica operativa (cartella `docs/`)
- documentazione normativa e di governance ([MANIFEST.md](../../MANIFEST.md), [instructions/](../../instructions/))

Le guide in `docs/` descrivono *come* utilizzare ed estendere il sistema.
I vincoli su *cosa è consentito o vietato*, i ruoli, i gate decisionali e le
macchine a stati sono definiti esclusivamente nelle fonti normative.

## Executive summary

Questo testo accompagna chi costruisce il sistema, ricordando che il valore è nel disegnare condizioni epistemiche condivise, non nel consegnare soluzioni autonome: ogni scelta tecnica nasce dal confronto con un contesto incerto e ogni modifica aggiorna una narrativa di responsabilità collettiva.

Il ruolo del developer è presidiare vincoli, tracciare l'incertezza e rendere esplicito ciò che non è ancora deciso, mantenendo la propria autorità e lasciando che il sistema resti uno strumento di supporto, mai una sostituzione del giudizio umano.

Per la cornice filosofica del progetto vedi [MANIFEST.md](../../MANIFEST.md).

Guida per sviluppare e manutenere **Timmy KB** in modo coerente e sicuro. Questa versione è la base iniziale della documentazione tecnica: niente riferimenti a legacy o migrazioni passate.
Per un percorso rapido step-by-step vedi anche [Developer Quickstart](developer_quickstart.md).

---

## Auxiliary developer tools

La cartella `tools/` contiene script di supporto per sviluppatori e manutentori
(migrazioni, smoke test, verifiche, utilita occasionali).
Questi strumenti non fanno parte del core runtime deterministico e possono
contenere fallback o comportamenti non deterministici.
Il loro uso e opzionale e contestuale.

- [`tools/gen_vision_yaml.py`](../../tools/gen_vision_yaml.py) - genera lo skeleton YAML del Vision Statement.
- [`tools/gen_dummy_kb.py`](../../tools/gen_dummy_kb.py) - genera workspace dummy per smoke test.
- [`tools/forbid_control_chars.py`](../../tools/forbid_control_chars.py) - verifica caratteri di controllo/encoding.
- [`tools/retriever_benchmark.py`](../../tools/retriever_benchmark.py) - benchmark rapido del retriever.
- [`tools/observability_stack.py`](../../tools/observability_stack.py) - avvio stack locale di osservabilita.

Per il core deterministico, le regole operative e le invarianti di runtime fanno
riferimento esclusivo a `src/`, `Coding Rules` e `Architecture Overview`.

## Obiettivi

Questa guida sintetizza gli obiettivi di qualita (SSoT, logging strutturato,
path-safety, import-safe, parita di firma, riproducibilita) come contesto
motivazionale. Le regole operative restano in [Coding Rules](coding_rule.md),
mentre la mappa dei componenti e dei confini e in
[Architecture Overview](../../system/architecture.md).

---

## ALERT / Workspace Discipline (non negoziabile)

Questa disciplina serve a separare artefacts versionati e derivatives runtime,
evitando che la repo root diventi stato operativo. Per regole vincolanti e
policy di workspace/igiene repo, fai riferimento a
[Coding Rules](coding_rule.md) e [Architecture Overview](../../system/architecture.md).

---

## Agency & Control Plane

- **WHAT:** la governance agency-first (ProtoTimmy → Timmy, Domain Gatekeepers, Control Plane/OCP, Prompt Chain) è documentata in `instructions/*` e definisce chi decide, valida ed esegue.
- **HOW:** i moduli `pipeline.*`, `semantic.*`, `workspace_bootstrap` e `WorkspaceLayout` sono strumenti operativi per I/O, path, logging e semantica; garantiscono artefacts affidabili (markdown arricchiti + knowledge graph validato) ma non orchestrano né decidono.
- La pipeline di foundation "apre" Timmy quando produce gli artefacts richiesti e il knowledge graph viene validato; fino a quel momento ProtoTimmy guida la fondazione e OCP gestisce il control plane senza porsi come agency.
- Ogni riferimento a `pipeline.*` in questo documento va inteso come HOW (strumento tecnico); le decisioni e i gate sono descritte nelle sezioni `instructions/00*`, `instructions/01*` e `instructions/02*`.

---

## Architettura in breve

Indice ragionato per leggere l'architettura completa:
Inizia dal [Repository Map](../../system/architecture.md#repository-map-root-level)
per capire la struttura del repo.
Poi passa al [Source Map](../../system/architecture.md#source-map-src) per i moduli runtime.
Le invarianti SSoT sono raccolte in
[Runtime Deterministic Core](../../system/architecture.md#runtime-deterministic-core-single-sources-of-truth).
Chiudi con [Responsibilities and boundaries](../../system/architecture.md#responsibilities-and-boundaries).

---

## Configurazione (SSoT)

Il file `config/config.yaml` resta la base per i parametri condivisi; esempio
illustrativo:

```yaml
ai:
  vision:
    model: gpt-4o-mini-2024-07-18   # modello per le chiamate dirette
    strict_output: true             # abilita validazioni strutturali quando necessario
    assistant_id_env: OBNEXT_ASSISTANT_ID  # usato solo dal flusso Assistant
```

Per regole operative e accesso runtime vedi
[Coding Rules](coding_rule.md#1bis-configurazione-ssot) e la guida di dettaglio in
[configurazione](configurazione.md).

### OIDC (opzionale)

Per i dettagli operativi e i placeholder vedi [configurazione](configurazione.md)
e `.env.example`.

### GitBook API

La preview usa HonKit via Docker ed e gestita via adapter/UI; per il flusso
operativo vedi runbook.

---

## Logging centralizzato

Il logging strutturato e la redazione dei segreti sono centrali per la
tracciabilita. Per regole vincolanti e pattern supportati vedi
[Coding Rules](coding_rule.md#3-logging-centralizzato) e
[Logging events](logging_events.md).

---

## Frontmatter (SSoT)

Il frontmatter e trattato come fonte canonica per i metadati dei markdown.
Per regole e API da usare vedi [Coding Rules](coding_rule.md#3bis-frontmatter-ssot).

---

## Path-safety & I/O sicuro

I percorsi workspace e l'I/O sicuro sono derivati da `WorkspaceLayout` e dagli
helper SSoT. Le regole vincolanti e gli esempi operativi sono in
[Coding Rules](coding_rule.md#5-i-o-sicuro--path-safety) e nel
[Runtime Deterministic Core](../../system/architecture.md#runtime-deterministic-core-single-sources-of-truth).

---

## Workspace SSoT (WorkspaceLayout)

`WorkspaceLayout` resta la fonte canonica per struttura e validazione. Per
invarianti, eccezioni e responsabilità vedi
[Coding Rules](coding_rule.md#percorsi-del-workspace-e-workspacelayout) e
[Architecture Overview](../../system/architecture.md#workspace-layout-ssot-of-structure).

---

## Retriever (ricerca)

Questa sezione descrive il comportamento atteso del retriever. I requisiti
operativi e la traccia dei log sono definiti in
[Coding Rules](coding_rule.md#6bis-retriever-ricerca) e in
[Logging events](logging_events.md).

---

## UI import-safe

La UI deve restare import-safe e senza I/O a import-time; i dettagli vincolanti
sono in [Coding Rules](coding_rule.md#7-ui-service-layer).

---

## Wrapper & Facade: parità di firma (SSoT)

I wrapper UI devono mantenere parita di firma e semantica rispetto al backend.
Le regole vincolanti sono in [Coding Rules](coding_rule.md#7-ui-service-layer).

---

## Gestione dipendenze (pip-tools)

Per policy di pin e rigenerazione requirements vedi
[Coding Rules](coding_rule.md#4-dipendenze-pip-tools).

---

## Qualità & CI

Per lint, typecheck, QA e hook CI fai riferimento a
[Coding Rules](coding_rule.md#8-test--qualita).

---

# Definition of Done - v1.0 Beta (Determinismo / Low Entropy)

La Definition of Done operativa e i criteri di determinismo sono normati in
[Coding Rules](coding_rule.md#8bis-definition-of-done---v1-0-beta-determinismo--low-entropy).

## Contributi

Per linee guida su commit, PR e test vedi [Coding Rules](coding_rule.md#10-git--pr-policy).
