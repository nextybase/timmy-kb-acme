# State Model (Beta 1.0)

## Scopo
Questo documento definisce il **modello di stato** del sistema in Beta 1.0 e il **contratto operativo** con cui lo stato viene derivato in modo deterministico dal **Decision Ledger** (SSoT).
Non introduce un "motore di stato": formalizza **termini, stati, transizioni e regole di interpretazione** per ridurre ambiguità ed entropia.

---

## Definizioni (SSoT-first)

### Workspace State (stato canonico)
Lo **stato del workspace** è la proiezione del **dato verificabile**:
**`workspace_state` = `to_state` dell'ultima decisione `ALLOW`**, ordinata per `decided_at` e tie-breaker `decision_id`.

Interpretazione: "cosa è *vero adesso* nel workspace", indipendentemente dall'esito dell'ultima run.

### Last Run Status (telemetria / health)
Lo **stato dell'ultima run** descrive "cosa è successo nell'ultima esecuzione":
- `latest_run` (run_id + started_at)
- `last_run_verdict` (ALLOW/DENY) e relativo gate/stage, se disponibile

Interpretazione: "l'ultima esecuzione è andata bene o male?".
Non sostituisce il `workspace_state`.

> Regola: **lo stato canonico è sempre `workspace_state`**. La run più recente è informazione di salute/telemetria.

---

## Stati canonici (Beta 1.0)

| Stato | Significato | Note |
|------|-------------|------|
| `NEW` | Workspace non pronto | Ingresso logico del flusso |
| `WORKSPACE_READY` | Struttura base pronta (cartelle + config) | Prodotto da pre_onboarding |
| `TAGS_CSV_READY` | CSV tag generato (checkpoint) | Percorso standard/strict |
| `TAGS_READY` | Stub semantico tag generato | **Solo dummy esplicito** |
| `SEMANTIC_READY` | Pipeline semantica completata | Richiede prerequisiti coerenti |

---

## Transizioni ammesse (Beta 1.0)

### Gate: pre_onboarding
- `NEW → WORKSPACE_READY` (ALLOW)
- `NEW → WORKSPACE_READY` (DENY) = tentativo fallito (target di transizione, non stato raggiunto)

### Gate: tag_onboarding
Percorso standard (default / strict):
- `WORKSPACE_READY → TAGS_CSV_READY` (ALLOW)

Percorso dummy (solo esplicito):
- `WORKSPACE_READY → TAGS_READY` (ALLOW) **solo se** `--dummy` e strict disattivo

Errori:
- `WORKSPACE_READY → TAGS_*` (DENY) = fallimento del gate (target non raggiunto)

### Gate: semantic_onboarding
- `TAGS_READY → SEMANTIC_READY` (ALLOW)
- `TAGS_READY → SEMANTIC_READY` (DENY) = fallimento del gate (target non raggiunto)

> Nota: se in Beta il percorso standard si ferma a `TAGS_CSV_READY`, l'esecuzione end-to-end richiede esplicitamente dummy per arrivare a `TAGS_READY` (vedi Policy).

---

## Semantica di ALLOW / DENY (regola di interpretazione)

### ALLOW
Una decisione `ALLOW` indica che la transizione è considerata **completata** e che gli artefatti previsti per quello stato sono stati **persistiti**.

### DENY
Una decisione `DENY` indica un **tentativo fallito**.
`to_state` in `DENY` rappresenta il **target della transizione**, non lo stato raggiunto.

> Regola: lo stato del workspace **non avanza mai** a causa di un `DENY`.

---

## Policy Strict vs Dummy (contratto operativo)

### Strict (`TIMMY_BETA_STRICT=1`)
- Blocca la generazione degli stub.
- In tag_onboarding lo stato massimo raggiungibile è `TAGS_CSV_READY`.
- È la modalità raccomandata per Beta in ambienti reali/dedicati.

### Dummy (`--dummy`)
- Abilita eccezionalmente la generazione degli stub end-to-end.
- È ammesso **solo** se esplicitamente richiesto tramite flag.
- Se strict è attivo, **dummy non ha effetto**.

### Auditabilità
Quando `--dummy` è usato:
- `evidence_json.dummy_mode = true`
- `rationale` contiene esplicitamente una traccia (es. `ok_dummy_mode`)

> Regola d'oro: se nel ledger compare `TAGS_READY`, allora **è stato usato dummy** (o si è violata la policy).

---

## Derivazione e reporting (ledger-status)

### Output minimo garantito
- `current_state` = `workspace_state` (ultimo ALLOW)
- `gates` = ultima decisione per gate (ordinamento stabile)
- `latest_run` = ultima run (se presente)

### Interpretazione operativa consigliata
- `workspace_state` risponde: "dove siamo davvero?"
- `latest_run + verdict` risponde: "l'ultima esecuzione è sana?"

Esempi:
- `workspace_state = SEMANTIC_READY` + ultima run DENY → workspace valido, ma **ultima esecuzione fallita** (health degradata).
- `workspace_state = TAGS_CSV_READY` + dummy_mode unknown → standard/strict, end-to-end non eseguito.

---

## Non previsto (intenzionale, Beta 1.0)
- Migrazioni/versioning del ledger
- Motore di inferenza dello stato oltre "latest decision"
- UI/Dashboard di stato
- Auto-promotion o fallback silenziosi

---

## Conseguenze pratiche (una riga)
Lo stato è una **proiezione verificabile del ledger**: chi legge il ledger deve poter ricostruire "cosa è vero" senza interpretazioni creative.
