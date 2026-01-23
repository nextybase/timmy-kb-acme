# SPDX-License-Identifier: GPL-3.0-only
## Ownership schema per cliente (slug)

Questo documento descrive lo schema canonico runtime consumato da `pipeline.ownership`. Altri concetti di governance non implementati non fanno parte del contratto Beta.

Per ogni `clients_db/clients/<slug>/ownership.yaml` si definisce l'ownership tenant-aware usata dal Control Plane; non è un artefatto dell'Epistemic Envelope.

### Schema YAML

- `schema_version` *(stringa, attesa)* - versione dello schema (default "1").
- `slug` *(stringa, atteso)* - slug del tenant; se presente deve combaciare con il path.
- `owners` *(mappatura, attesa)* - chi ha ownership per i ruoli canonici. Se omessa, viene trattata come mappa vuota.
  - `user` *(lista di stringhe, anche vuota)* - owner delle attività UI per il tenant.
  - `dev` *(lista di stringhe, anche vuota)* - owner delle automazioni CLI/tools per il tenant.
  - `architecture` *(lista di stringhe, anche vuota)* - owner dei guardrail e della compliance architetturale per il tenant.

È vietato definire ruoli diversi da `user`, `dev`, `architecture`.

### Esempio

```yaml
schema_version: "1"
slug: "acme"
owners:
  user:
    - "@nextybase/user-channel"
  dev:
    - "@nextybase/dev-channel"
  architecture:
    - "@nextybase/architecture"
```

### Invarianti

1. I riferimenti sono solo a identità/team placeholder: possono essere alias (es. `@nextybase/user-channel`); nessun nome personale deve apparire.
2. Il file è versionato insieme alle policy del Control Plane; aggiornarlo richiede la stessa pipeline di QA.
3. La presenza del file non duplica CODEOWNERS: quest'ultimo gestisce review GitHub, mentre l'ownership per slug descrive il contract di cross-channel coordination.
4. Il file `clients_db/clients/example/ownership.yaml` funge da template canonico. L'ownership per slug viene generata copiando questo template e impostando `slug` al valore corrispondente.

### Nota su "superadmin"

Il concetto di "superadmin" è organizzativo/umano, non fa parte dello schema runtime 1.0 Beta e non è consumato da `pipeline.ownership`.
