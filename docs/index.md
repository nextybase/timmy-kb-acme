# Timmy-KB - Documentazione (v1.0 Beta)

Benvenuto nella documentazione di **Timmy-KB**. Qui trovi architettura, guida utente, guida sviluppatore, policy operative e regole di versioning.

> **Lingue**: la documentazione operativa rimane in italiano; il documento di architettura (`architecture.md`) resta in inglese per coerenza con diagrammi e naming del codice.

> **Doppio approccio**: puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
> Avvio interfaccia: `streamlit run onboarding_ui.py` - vedi [Guida UI (Streamlit)](guida_ui.md).

## Indice

- **Guide**
  - [User Guide](user_guide.md) - utilizzo della pipeline (pre-onboarding, tagging, semantic onboarding, push).
  - [Architettura del sistema](architecture.md) - componenti, flussi end-to-end, API interne.
  - [Developer Guide](developer_guide.md) - principi architetturali, redazione log, test suggeriti.
  - [Coding Rules](coding_rule.md) - stile, tipizzazione, logging, I/O sicuro, atomicita', versioning.
  - [Configurazione (YAML, .env, OIDC)](configurazione.md) - SSoT, segreti, wiring OIDC.
  - [Configuration (EN)](configuration.md) - overview di configurazione in inglese.
  - [Interfaccia Streamlit ](streamlit_ui.md) - Regole di coding per Streamlit 1.50.0.
  - [Test suite](test_suite.md) - test smoke e suite PyTest.
  - [Guida UI (Streamlit)](guida_ui.md) - interfaccia grafica; **avvio rapido**: `streamlit run onboarding_ui.py`.
  - Type checking rapido: `make type` (mypy), `make type-pyright` (pyright/npx)
- **Policy**
  - [Policy di Versioning](versioning_policy.md) - SemVer, naming tag e branch, compatibilita'.
  - [Policy di Push](policy_push.md) - requisiti, protezioni branch, force-with-lease, mascheramento token.
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
- **Agente Codex**
  - [Codex Integrazione](codex_integrazione.md) - uso di Codex in VS Code come coding agent, regole AGENTS.md e configurazione avanzata.
  - [Runbook Codex](runbook_codex.md) - flussi operativi per l'uso di Codex.
  - [AGENTS (Repo)](AGENTS.md) - regole locali per gli agent.
  - [AGENTS Index](AGENTS_INDEX.md) - indice delle policy per agent e preferenze.
- **Changelog**
  - [CHANGELOG](../CHANGELOG.md) - novita' e fix per ogni release.
- **Milestones**
  - [Archive cleanup](milestones/archive_cleanup.md) - milestone archiviate e cleanup pianificati.

> La config bootstrap globale vive in `config/config.yaml`. La config *per cliente* e' in `output/timmy-kb-<slug>/config/config.yaml`.
