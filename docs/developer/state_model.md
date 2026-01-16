# State Model (Beta 1.0)

## Scopo
Questo documento definisce il **modello di stato** del sistema in Beta 1.0 e il **contratto operativo** con cui lo stato viene derivato in modo deterministico dal **Decision Ledger** (SSoT).
Non introduce un "motore di stato": formalizza **termini, stati, transizioni e regole di interpretazione** per ridurre ambiguità ed entropia.

---

## Definizioni (SSoT-first)

### Workspace State (stato canonico)
Lo **stato del workspace** è la proiezione del **dato verificabile**:
**`workspace_state` è derivato esclusivamente dal Decision Ledger e ancorato alla `latest_run`**.

Interpretazione: "cosa è *vero adesso* nel workspace", perché la `latest_run` è quella che ha definito l'assetto corrente degli artefatti.

Regola formale (Beta):
- `latest_run` = ultima entry in `runs` (ordering deterministico)
- `workspace_state` = `to_state` dell'ultima decisione `ALLOW` **nella `latest_run`**, ordinata per `decided_at` e tie-breaker `decision_id`

> Nota: questa scelta evita la "composizione" di gate provenienti da run diverse.

### Last Run Status (telemetria / health)
Lo **stato dell'ultima run** descrive "cosa è successo nell'ultima esecuzione":
- `latest_run` (run_id + started_at)
- `last_run_verdict` (ALLOW/DENY) e relativo gate/stage, se disponibile

Interpretazione: "l'ultima esecuzione è andata bene o male?".
Non sostituisce il `workspace_state`.

> Regola: **lo stato canonico è sempre `workspace_state`** e deriva dalla `latest_run`. La run più recente è anche il riferimento per la telemetria/health.

---

## Monotonicità e regressione (Beta)
In Beta, lo stato **non è monotono**: è ammessa **regressione** se una run successiva sostituisce gli artefatti e quindi ridefinisce uno stato "più basso".

Esempio: se una run successiva rigenera solo il CSV tag (senza stub), lo stato canonico può passare da `TAGS_READY` a `TAGS_CSV_READY`.

---

## Stati canonici (Beta 1.0)

| State | Significato | Trigger |
|---|---|---|
| NEW | Workspace iniziale non ancora bootstrap | nessuna run o decisione |
| WORKSPACE_READY | Pre-onboarding completato | pre_onboarding ALLOW |
| TAGS_CSV_READY | CSV tag generato / checkpoint raggiunto | tag_onboarding ALLOW (checkpoint) |
| TAGS_READY | Stub semantico completato | tag_onboarding ALLOW (dummy) |
| SEMANTIC_READY | Onboarding semantico completato | semantic_onboarding ALLOW |

---

## Transizioni canoniche (Beta)

### pre_onboarding
- `NEW` -> `WORKSPACE_READY`

### tag_onboarding
- default: `WORKSPACE_READY` -> `TAGS_CSV_READY`
- dummy: `WORKSPACE_READY` -> `TAGS_READY`

### semantic_onboarding
- `TAGS_READY` -> `SEMANTIC_READY`

---

## Dummy mode (audit)

Quando `--dummy` è usato:
- `evidence_json` include `dummy_mode: true`
- `rationale` contiene il substring `"dummy"`
- lo stato target può essere `TAGS_READY`

---

## Derivazione e reporting (ledger-status)

### Output minimo garantito
- `latest_run` = ultima run (se presente)
- `current_state` = `workspace_state` (ultimo `ALLOW` **nella latest_run**)
- `gates` = ultime decisioni per gate **nella latest_run** (ordinamento stabile)

### Interpretazione operativa consigliata
- `workspace_state` risponde: "dove siamo davvero?"
- `latest_run + verdict` risponde: "l'ultima esecuzione è sana?"
