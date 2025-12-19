# SPDX-License-Identifier: GPL-3.0-only
## Ownership schema per cliente (slug)

Per ogni `clients/<slug>/ownership.yaml` si definisce l'ownership tenant-aware che si aggiunge alle ownership repo-level (CODEOWNERS) e ai guardrail globali.

### Schema YAML

- `superadmin` *(stringa, obbligatorio)* – identità privilegiata (es. `@nextybase/ops`) sempre responsabile delle escalation.
- `ownership` *(mappatura, obbligatoria)* – chi ha ownership per i ruoli canonici.
  - `user` *(lista di stringhe, anche vuota)* – owner delle attività UI per il tenant.
  - `dev` *(lista di stringhe, anche vuota)* – owner delle automazioni CLI/tools per il tenant.
  - `architecture` *(lista di stringhe, anche vuota)* – owner dei guardrail e della compliance architetturale per il tenant.

È vietato definire ruoli diversi da `user`, `dev`, `architecture` e `superadmin`.

### Esempio

```yaml
superadmin: "@nextybase/ops"
ownership:
  user:
    - "@nextybase/user-channel"
  dev:
    - "@nextybase/dev-channel"
  architecture:
    - "@nextybase/architecture"
```

### Invarianti

1. I riferimenti sono solo a identità/team placeholder: possono essere alias (es. `@nextybase/user-channel`); nessun nome personale deve apparire.
2. Il file è versionato insieme ai dati del cliente; aggiornarlo richiede la stessa pipeline di QA.
3. La presenza del file non duplica CODEOWNERS: quest'ultimo gestisce review GitHub, mentre l'ownership per slug descrive il contract di cross-channel coordination.
4. Il file `clients/example/ownership.yaml` funge da template canonico. L'ownership per slug viene generata copiando questo template e settando `slug` al valore corrispondente quando viene creato un nuovo workspace.

### SuperAdmin globale

- `TIMMY_GLOBAL_SUPERADMINS` *(stringa, opzionale)*: lista CSV di email/handle che rappresentano i SuperAdmin globali. I valori vengono splittati e validati (non devono contenere spazi). Il modulo `pipeline.ownership` espone `get_global_superadmins()` per leggerli.

Il campo `superadmin` tenant-level rimane obbligatorio per ogni `ownership.yaml`. Il valore globale è usato come capability informativa e non influisce ancora sul controllo permessi.
