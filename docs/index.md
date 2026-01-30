# Timmy-KB - Documentazione (v1.0 Beta)

Benvenuto nella documentazione di **Timmy-KB**.
Questo spazio raccoglie i materiali necessari a comprendere, usare e mantenere il sistema, mantenendo una separazione chiara tra **contesto concettuale**, **regole vincolanti** e **operatività tecnica**.

Timmy-KB è un ambiente di creazione e governo che traduce operativamente i principi di **NeXT** attraverso una pipeline di fondazione e un assistente (Timmy) che opera sempre sotto **Human-in-the-Loop**.
Per la cornice valoriale ed epistemica di riferimento consulta il file `MANIFEST.md` alla root del repository.

> **Nota sulle lingue**\
> La documentazione operativa è in italiano. Il documento di architettura (`system/architecture.md`) resta in inglese per coerenza con diagrammi, naming e codice.

---

## Come orientarsi

La documentazione è organizzata per **ruolo e funzione**. Usa l'indice seguente come mappa di navigazione, non come ordine di lettura obbligatorio.

## Normative context

Questo progetto adotta una separazione intenzionale tra:
- documentazione tecnica operativa (cartella `docs/`)
- documentazione normativa e di governance ([MANIFEST.md](../MANIFEST.md), [instructions/](../instructions/))

Le guide in `docs/` descrivono *come* utilizzare ed estendere il sistema.
I vincoli su *cosa è consentito o vietato*, i ruoli, i gate decisionali e le
macchine a stati sono definiti esclusivamente nelle fonti normative.
Vedi anche: `instructions/13_artifacts_policy.md` (core vs service artifacts, fallback e determinismo).

---

## Entry point

- **[README della documentazione](README.md)**\
  Introduzione alla struttura e ai criteri di organizzazione dei documenti.

- **Quickstart**

  - [User Quickstart](user/quickstart.md)
  - [Developer Quickstart](developer/developer_quickstart.md)

- **Installazione**
  - [Guida installazione](user/insitallation_guide.md)

---

## User documentation (`docs/user/`)

Guida per chi **utilizza Timmy-KB** tramite UI o CLI.

- **[Guida installazione](user/insitallation_guide.md)** - setup passo-passo (software, venv, dipendenze, test architettura, avvio UI).
- **[User Guide](user/user_guide.md)** - utilizzo della pipeline (pre-onboarding, tagging, semantic onboarding, preview).
- **[Arricchimento semantico](user/arricchimento.md)** - flusso completo UI/CLI, generazione tag, euristica vs SpaCy.

Questi documenti descrivono **cosa fa il sistema e cosa osserva l'utente**, senza introdurre regole normative.

---

## Developer documentation (`docs/developer/`)

Materiali per chi **sviluppa o mantiene Timmy-KB**.

- **[Developer Guide](developer/developer_guide.md)** - contesto e onboarding (non normativo).
- **[Developer Quickstart](developer/developer_quickstart.md)** - percorsi minimi di lavoro (CLI/UI).
- **[Coding Rules](developer/coding_rule.md)** - stile, tipizzazione, logging, I/O sicuro.
- **[Configurazione](developer/configurazione.md)** - YAML, `.env`, SSoT, wiring OIDC.
- **[Streamlit UI](developer/streamlit_ui.md)** - regole di coding per l'interfaccia.
- **[Explainability overview](developer/explainability_overview.md)** - segnali, lineage e tracciabilità.
- **[Revisione pipeline di trasformazione](developer/data_transformation_review.md)** - stato e note evolutive della pipeline di fondazione.
- **[Code Review Senior](developer/code_review_senior.md)** - sintesi ricorrente delle review tecniche.

Questa sezione spiega **come funziona e come evolve il sistema**, non cosa è consentito o vietato.

---

## Policy (`docs/policies/`)

Documentazione **derivata/applicativa** (vincolante solo come applicazione delle regole in `MANIFEST.md` e `instructions/*`).
Ordine di precedenza: `MANIFEST.md` -> `instructions/*` -> codice -> `docs/` (incl. `docs/policies/`).

Qui vivono le regole operative che definiscono i confini del sistema:

- **[Policy di versioning](policies/versioning_policy.md)** - SemVer, naming, compatibilità.
- **[Security & compliance](policies/security.md)** - segreti, OIDC, branch protection.
- **[Contratti operativi](policies/import_contract.md)** - import/export, invarianti di pipeline.
- **[Core rules per assistant](policies/next_core_for_assistants.md)** - regole comuni per i moduli AI nell'ecosistema NeXT.
- **[Environment certification](policies/environment_certification.md)** - requisiti per ambiente certificato e run conformi.

Se un comportamento viola un documento in questa sezione, è da considerarsi un errore nel perimetro applicativo, senza sovrascrivere `MANIFEST.md` o `instructions/*`.

---

## Context & alignment (`docs/context/`)

Documenti di **allineamento concettuale e boundary**.

- **[NeXT alignment](context/next_alignment.md)** - mappa tra principi NeXT e implementazione Timmy-KB.
- **[NeXT boundary](context/next_boundary.md)** - cosa Timmy-KB non implementa o delega rispetto al framework teorico.

Questi file non sono guide né policy: servono a chiarire **perimetro, limiti e senso del sistema**, soprattutto in fase di review, audit o onboarding avanzato.

---

## ADR - Architecture Decision Records (`docs/adr/`)

Registro delle principali decisioni architetturali.

- **[ADR index](adr/README.md)** - panoramica delle decisioni.
- ADR specifici (SQLite come SSoT, separazione segreti/config, E2E UI, NLP tuning, …).

Gli ADR sono **scritti per esseri umani**, ma **leggibili dagli agenti** come fonte di contesto decisionale e storico.

---

## Observability

- **[Observability stack](developer/observability.md)** - Loki, Promtail, Grafana, tracing.
- **[Logging events](developer/logging_events.md)** - nomenclatura e struttura degli eventi log.

---

## Agent & tooling

- **[Guida Codex](developer/guida_codex.md)** - uso di Codex come coding agent.
- **[Runbook Codex](../system/ops/runbook_codex.md)** - flussi operativi.
- **[AGENTS (repo)](policies/AGENTS.md)** - regole locali per gli agent.
- **[AGENTS index](../system/ops/agents_index.md)** - indice delle policy per agent.
- **[Prompt Chain spec](../system/specs/promptchain_spec.md)** - modello SSoT per orchestrazione planner/OCP.

---

## Changelog

- **[CHANGELOG](../CHANGELOG.md)** - novità e fix per release.

---

> **Nota finale sulla configurazione**\
> La configurazione globale vive in `config/config.yaml`.\
> La configurazione per cliente è in `output/timmy-kb-<slug>/config/config.yaml`.
