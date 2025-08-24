# docs/index.md
# Timmy-KB — Documentazione (v1.2.1)

Benvenuto nella documentazione di **Timmy-KB**. Qui trovi architettura, guida utente, guida sviluppatore, policy operative e regole di versioning.

## Indice

- **Panoramica & Architettura**
  - [Architettura del sistema](architecture.md) – componenti, flussi end-to-end, API interne.
- **Guide**
  - [User Guide](user_guide.md) – utilizzo della pipeline (pre-onboarding, tagging, semantic onboarding, push).
  - [Developer Guide](developer_guide.md) – principi architetturali, redazione log, refactor orchestratori, test suggeriti.
  - [Coding Rules](coding_rules.md) – stile, tipizzazione, logging, I/O sicuro, atomicità, versioning.
- **Policy**
  - [Policy di Versioning](versioning_policy.md) – SemVer, naming tag e branch, compatibilità.
  - [Policy di Push](policy_push.md) – requisiti, protezioni branch, force-with-lease, mascheramento token.
- **Changelog**
  - [CHANGELOG](CHANGELOG.md) – novità e fix per ogni release.

## Novità v1.2.1 (estratto)

- **Split orchestratori**: `semantic_onboarding.py` (conversione + enrichment + preview) e `onboarding_full.py` (solo push).
- **SSoT path-safety**: `ensure_within` spostato in `pipeline.path_utils`.
- **Adapter contenuti**: fallback README/SUMMARY uniformi e atomici.
- **Doc aggiornata**: Architecture, User e Developer Guide, Policy.

> La config bootstrap globale vive in `config/config.yaml`. La config *per cliente* è in `output/timmy-kb-<slug>/config/config.yaml`.
