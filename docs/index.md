# Timmy-KB - Documentazione (v1.0 Beta)

Benvenuto nella documentazione di **Timmy-KB**. Qui trovi architettura, guida utente, guida sviluppatore, policy operative e regole di versioning.

> **Lingue**: la documentazione operativa rimane in italiano; il documento di architettura (`architecture.md`) resta in inglese per coerenza con diagrammi e naming del codice.

> **Doppio approccio**: puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.
> Avvio interfaccia: `streamlit run onboarding_ui.py` - vedi [Guida UI (Streamlit)](guida_ui.md).

## Indice

- **Panoramica & Architettura**
  - [Architettura del sistema](architecture.md) - componenti, flussi end-to-end, API interne.
- **Guide**
  - [User Guide](user_guide.md) - utilizzo della pipeline (pre-onboarding, tagging, semantic onboarding, push).
  - [Developer Guide](developer_guide.md) - principi architetturali, redazione log, test suggeriti.
  - [Coding Rules](coding_rule.md) - stile, tipizzazione, logging, I/O sicuro, atomicità, versioning.
  - [Configurazione (.env vs config)](configuration.md) - separazione segreti/config, esempi e tooling.
  - [Interfaccia Streamlit ](streamlit_ui.md) - Regole di coding per Streamlit 1.50.0.
  - [Test suite](test_suite.md) - test smoke e suite PyTest.
  - [Guida UI (Streamlit)](guida_ui.md) - interfaccia grafica; **avvio rapido**: `streamlit run onboarding_ui.py`.
  - [Codex Integrazione](codex_integrazione.md) - uso di Codex in VS Code come coding agent, regole AGENTS.md e configurazione avanzata.
  - Type checking rapido: `make type` (mypy), `make type-pyright` (pyright/npx)
- **Policy**
  - [Policy di Versioning](versioning_policy.md) - SemVer, naming tag e branch, compatibilità.
  - [Policy di Push](policy_push.md) - requisiti, protezioni branch, force-with-lease, mascheramento token.
  - [Security & Compliance](security.md) - gestione segreti, OIDC, branch protection, hook locali.
  - [Registro decisioni (ADR)](adr/README.md) - contesto delle scelte tecniche.
- **Observability**
  - [Observability Stack](observability.md) - Loki/Promtail/Grafana, trace_id/span_id, query utili.
- **Changelog**
  - [CHANGELOG](../CHANGELOG.md) - novità e fix per ogni release.

> La config bootstrap globale vive in `config/config.yaml`. La config *per cliente* è in `output/timmy-kb-<slug>/config/config.yaml`.
