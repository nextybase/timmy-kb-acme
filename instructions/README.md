# instructions/ - Specifica normativa del Control Plane (Beta 1.0)

## Cos'è `instructions/`
- **Design-first specification repository** del control plane ProtoTimmy.
- **Single Source of Truth (SSoT)** per la governance operativa della Beta 1.0.
- **NON** è documentazione descrittiva o narrativa.
- **NON** è implementazione.
- È un deposito di **contratti operativi verificabili**.

Ogni file in questa cartella:
- definisce **ruoli, responsabilità, stati, gate, transizioni e artefatti**;
- impone **invarianti e failure modes espliciti**;
- produce o richiede **artefatti verificabili** (Decision Record, stati, log, stop_code).

Se un comportamento non è descritto qui, **non è ammesso** nel sistema.

---

## Obiettivo finale (Definition of Done - Beta 1.0)
- L'interazione utente avviene **esclusivamente tramite Timmy (ProtoTimmy)**.
- Timmy orchestra Domain Gatekeepers e micro-agent con copertura completa e HiTL esplicito.
- OCP (Engineering Gatekeeper) dirige Codex e i micro-agent tramite il Control Plane.
- La Prompt Chain è **lineare, governata e osservabile**, con:
  - transizioni di fase esplicite,
  - failure mode dichiarati,
  - stop rumorosi (no degradazione silenziosa).
- La pipeline dati è governata end-to-end fino alla produzione dei markdown operativi finali.

---

## Regole non negoziabili (Beta 1.0)
- **Ogni transizione di stato produce un Decision Record canonico append-only**
  (PASS / BLOCK / FAIL / PASS_WITH_CONDITIONS).
- **Lo stato non è dedotto** da combinazioni di file o segnali:
  è attestato esclusivamente da Decision Record.
- Separazione netta tra:
  - **WHAT** (contratti, invarianti, gate, failure modes),
  - **HOW** (implementazione, codice, tooling).
- Nessuna ambiguità su:
  - chi decide (Timmy),
  - chi valida (Domain Gatekeepers / OCP),
  - chi esegue (micro-agent).
- **Nessun fallback implicito**, nessuna retro-compatibilità, nessuno shim:
  - ogni stop, errore o deviazione è esplicita,
  - con owner, trigger e regola di ripresa dichiarata.
- Runtime operativo **strict**: se non si può attestare uno stato, il sistema si ferma.

---

## Elenco dei documenti (stato Beta 1.0)

- `00_ssot_agency.md` - **congelato**
- `01_intents_and_actions.md` - **attivo**
- `02_prompt_chain_lifecycle.md` - **attivo**
- `03_gatekeepers_contracts.md` - **attivo**
- `04_microagents_work_orders.md` - **attivo**
- `05_pipeline_workspace_state_machine.md` - **attivo**
- `06_promptchain_workspace_mapping.md` - **attivo**
- `07_gate_checklists.md` - **attivo**
- `08_gate_evidence_and_retry_contract.md` - **attivo**
- `09_context_layout_contract_beta.md` - **congelato**
- `10_runtime_strict_contract_beta.md` - **attivo** - Runtime invariants and strict-only execution rules (Beta 1.0).

Un documento **attivo** può essere raffinato, ma:
- non può contraddire le invarianti di questo README;
- non può introdurre fallback o stati impliciti.

---

## Come lavorare sui documenti
- Eseguire **micro-planning verbale** prima di modificare qualsiasi file.
- Allineare ogni modifica alla terminologia ufficiale:
  Timmy / ProtoTimmy, Domain Gatekeepers, Control Plane, micro-agent.
- Evitare terminologia nuova o non allineata.
- Preferire:
  - tabelle,
  - checklist,
  - invarianti,
  - failure modes,
  a spiegazioni discorsive.
- Scrivere in **tono normativo**, con frasi operative e verificabili.

---

## Avvertenza finale
Questo README è la **porta di ingresso normativa** della Beta 1.0:
- ogni refactor di governance parte da qui;
- ogni implementazione futura deve potersi mappare a questi contratti;
- ogni discrepanza tra codice e questa specifica è un **bug**, non una scelta.

Se la documentazione e il codice divergono, **vince la documentazione**.
