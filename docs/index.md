# Timmy-KB - Documentazione (v1.0 Beta)

Benvenuto nella documentazione di **Timmy-KB**: sistema di creazione governata che traduce tecnicamente i principi di NeXT, con la pipeline di fondazione che costruisce la KB e l’assistente Timmy operativo sotto controllo umano (Human-in-the-Loop). Questo spazio mostra il “come” concreto mantenendo l’envelope epistemico e l’orchestrazione di agenti HiTL/micro-agenti; per la cornice valoriale consulta [MANIFEST.md](../MANIFEST.md).

- **Lingue**: la documentazione operativa rimane in italiano; il documento di architettura (`../system/architecture.md`) resta in inglese per coerenza con diagrammi e naming del codice.

> **Doppio approccio**: puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
- Avvio interfaccia: `streamlit run onboarding_ui.py` - vedi [Guida UI (Streamlit)](user/guida_ui.md).

## Indice

- **Guide**
  - [User Guide](user/user_guide.md) - utilizzo della pipeline (pre-onboarding, tagging, semantic onboarding, preview Docker).
  - [Arricchimento semantico](arricchimento.md) - flusso UI/CLI, tag, euristica vs SpaCy.
  - [Architettura del sistema](../system/architecture.md) - componenti, flussi end-to-end, API interne.
  - [Next Core per Assistant](next_core_for_assistants.md) - linee guida NeXT per moduli OpenAI (context operativo Timmy-KB).
  - [Developer Guide](developer/developer_guide.md) - principi architetturali, redazione log, test suggeriti.
  - [Developer Quickstart](developer/developer_quickstart.md) - happy path minimi (CLI e UI).
  - [Coding Rules](developer/coding_rule.md) - stile, tipizzazione, logging, I/O sicuro, atomicita', versioning.
  - [Revisione pipeline di trasformazione](data_transformation_review.md) - strumenti della pipeline di fondazione e aggiornamenti.
  - [NeXT alignment](next_alignment.md) - allineamento NeXT ↔ Timmy-KB per auditor e developer.
  - [NeXT boundary](next_boundary.md) - limiti tra NeXT teorico e implementazione Timmy-KB.
  - [Configurazione (YAML, .env, OIDC)](configurazione.md) - SSoT, segreti, wiring OIDC.
  - [Configuration (EN)](configurazione.md) - overview di configurazione in inglese.
  - [Interfaccia Streamlit ](streamlit_ui.md) - Regole di coding per Streamlit 1.50.0.
  - [Test suite](test_suite.md) - test smoke e suite PyTest.
  - [Explainability overview](explainability_overview.md) - segnale/lineage delle risposte.
  - [Guida UI (Streamlit)](user/guida_ui.md) - interfaccia grafica; **avvio rapido**: `streamlit run onboarding_ui.py`.
  - Type checking rapido: `make type` (mypy), `make type-pyright` (pyright/npx)
- **Policy**
  - [Policy di Versioning](versioning_policy.md) - SemVer, naming tag e branch, compatibilita'.
  - [Security & Compliance](security.md) - gestione segreti, OIDC, branch protection, hook locali.
- **ADR - scelte tecniche**
  - [Registro decisioni (ADR)](adr/README.md) - contesto delle scelte tecniche.
    - [ADR 0001 - SQLite SSOT dei tag](adr/0001-sqlite-ssot-tags.md)
    - [ADR 0002 - Separation secrets/config](adr/0002-separation-secrets-config.md)
    - [ADR 0003 - Playwright E2E UI](adr/0003-playwright-e2e-ui.md)
    - [ADR 0004 - NLP performance tuning](adr/0004-nlp-performance-tuning.md)
- **Observability**
  - [Observability Stack](observability.md) - Loki/Promtail/Grafana, trace_id/span_id, query utili.
  - [Logging Events](logging_events.md) - eventi log strutturati e nomenclatura.
- [Code Review Senior](developer/code_review_senior.md) - sintesi delle review tecniche + quick wins sulle policy di logging/tracing.
- **Agente Codex**
  - [Guida Codex](guida_codex.md) - uso di Codex in VS Code come coding agent, regole AGENTS.md e configurazione avanzata.
  - [Runbook Codex](../system/ops/runbook_codex.md) - flussi operativi per l'uso di Codex.
  - [AGENTS (Repo)](AGENTS.md) - regole locali per gli agent.
  - [AGENTS Index](../system/ops/agents_index.md) - indice delle policy per agent e preferenze.
  - Prompt Chain Spec: [PromptChain_spec](../system/specs/promptchain_spec.md) - modello SSoT per orchestrazione Planner/OCP/Codex e chiusura QA.
- **Changelog**
  - [CHANGELOG](../CHANGELOG.md) - novita' e fix per ogni release.
- **Milestones**
  - [Archive cleanup](milestones/archive_cleanup.md) - milestone archiviate e cleanup pianificati.

> La config bootstrap globale vive in `config/config.yaml`. La config *per cliente* e' in `output/timmy-kb-<slug>/config/config.yaml`.
