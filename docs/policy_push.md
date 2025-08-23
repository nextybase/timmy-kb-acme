# Policy di Push — Timmy-KB (v1.1.0)

Questa policy stabilisce le regole per pubblicare in GitHub i contenuti generati dalla pipeline di onboarding. L’obiettivo è garantire sicurezza, tracciabilità e allineamento con la strategia di versioning.

---

## 1) Regola base: push incrementale

- **Default**: il push è **incrementale**, senza sovrascrivere la storia remota.
- La pipeline effettua:
  - `git pull --rebase` → aggiorna il branch remoto.
  - Commit solo se ci sono differenze.
  - `git push` senza `--force`.
- In caso di conflitto non risolvibile: l’orchestratore solleva `PushError` con messaggi chiari.

---

## 2) Force push (governance)

Il force push è **vietato di default**. È consentito solo se:

- Lanciato con **due fattori**:
  - Flag CLI `--force-push`
  - Flag CLI `--force-ack <TAG>`
- Il branch target è incluso in `GIT_FORCE_ALLOWED_BRANCHES` (es. `main`, `release/*`).
- In questo caso, viene usato `--force-with-lease` per prevenire sovrascritture non intenzionali.
- Il commit riceve un trailer `Force-Ack: <TAG>` per auditabilità.

Se uno dei requisiti manca, l’orchestratore esce con `ForcePushError`.

---

## 3) Variabili d’ambiente

- `GITHUB_TOKEN` → token obbligatorio per il push.
- `GIT_DEFAULT_BRANCH` → branch di default (fallback `main`).
- `GIT_FORCE_ALLOWED_BRANCHES` → lista (separata da virgola) di branch su cui è permesso il force.

---

## 4) Redazione log

- Tutti i comandi Git e gli header HTTP vengono loggati **senza segreti**.
- Token e ack sono mascherati (`***`).
- Abilitazione redazione tramite `LOG_REDACTION` (`auto`/`on`/`off`).

---

## 5) Note operative

- **CI/CD**: in ambienti automatizzati il force richiede entrambi i flag; in assenza, la pipeline fallisce.
- **Auditabilità**: i log includono `local_sha`, `remote_sha` e trailer di commit.
- **Raccomandazione**: evitare force push su `main`, preferire branch dedicati e PR.

---

## 6) Compatibilità

- Nessun breaking change: i flussi di push storici restano validi.
- Le regole di governance rendono il comportamento **safe by default**.

