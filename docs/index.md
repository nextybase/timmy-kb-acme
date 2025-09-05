# Timmy-KB - Documentazione (v1.7.0)

Benvenuto nella documentazione di **Timmy-KB**. Qui trovi architettura, guida utente, guida sviluppatore, policy operative e regole di versioning.

> **Doppio approccio**: puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.  
> Avvio interfaccia: `streamlit run onboarding_ui.py` - vedi [Guida UI (Streamlit)](guida_ui.md).

## Indice

- **Panoramica & Architettura**
  - [Architettura del sistema](architecture.md) - componenti, flussi end-to-end, API interne.
- **Guide**
  - [User Guide](user_guide.md) - utilizzo della pipeline (pre-onboarding, tagging, semantic onboarding, push).
  - [Developer Guide](developer_guide.md) - principi architetturali, redazione log, refactor orchestratori, test suggeriti.
  - [Coding Rules](coding_rule.md) - stile, tipizzazione, logging, I/O sicuro, atomicità, versioning.
  - [Test suite](test_suite.md) - Test smoke e Pydantic.
  - [Guida UI (Streamlit)](guida_ui.md) - interfaccia grafica; **avvio rapido**: `streamlit run onboarding_ui.py`.
  - [Codex Integrazione](codex_integrazione.md) - uso di Codex in VS Code come coding agent, regole AGENTS.md e configurazione avanzata.
- **Policy**
  - [Policy di Versioning](versioning_policy.md) - SemVer, naming tag e branch, compatibilità.
  - [Policy di Push](policy_push.md) - requisiti, protezioni branch, force-with-lease, mascheramento token.
- **Changelog**
  - [CHANGELOG](../CHANGELOG.md) - novità e fix per ogni release.

> La config bootstrap globale vive in `config/config.yaml`. La config *per cliente* è in `output/timmy-kb-<slug>/config/config.yaml`.

