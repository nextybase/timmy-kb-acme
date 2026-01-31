# 08 - Gate Evidence and Retry Contract (SSoT)

**Status:** ACTIVE
**Authority:** Single Source of Truth (SSoT)
**Scope:** definizione normativa dei contratti dei Gate
(Evidence / Skeptic / QA), del modello di evidenza,
dei predicate di stato e della policy di retry/resume.

Il binding lifecycle ↔ workspace ↔ gate ↔ Decision Record
è definito in `instructions/06_promptchain_workspace_mapping.md`.

Questo documento **non definisce flussi**:
definisce **le condizioni formali che permettono ai gate di attestare uno stato**.

---

## Principi Fondativi (Beta 1.0)
- **Ogni transizione di stato produce un Decision Record append-only.**
- Nessun gate produce "PASS impliciti" o dedotti da log.
- I log sono **evidenze**, non artefatti di verità.
- In assenza di Decision Record, **la transizione non è avvenuta**.
- Retry ≠ resume: ogni retry è una **nuova run attestata**.

---

## Decision Record (Artefatto Canonico)

Il **Decision Record** è l'unico output normativo dei gate.

### Schema minimo obbligatorio
- `decision_id` (univoco, append-only)
- `run_id`
- `slug`
- `from_state`
- `to_state` (presente solo se PASS)
- `verdict` (`PASS | BLOCK | FAIL | PASS_WITH_CONDITIONS`)
- `actor` (`gatekeeper:<name>` | `timmy`)
- `timestamp` (UTC)
- `evidence_refs[]` (puntatori a log e/o artefatti)
- `stop_code` (obbligatorio se BLOCK/FAIL)

I log e i file **non sostituiscono** mai questo record.

---

## Persistenza nel Decision Ledger (mapping normativo → SQLite)

Implementazione attuale: tabella `decisions` in `config/ledger.db` (SQLite).
La persistenza **non cambia schema** e mappa i campi normativi nel ledger così:

### Mapping verdict
- `PASS` → `ALLOW` (ledger), `to_state` obbligatorio
- `PASS_WITH_CONDITIONS` → `ALLOW` (ledger), `to_state` obbligatorio, `conditions` obbligatorio
- `BLOCK` / `FAIL` → `DENY` (ledger), `stop_code` obbligatorio, `to_state` richiesto come *target* (vincolo schema)

### Mapping campi
- `gate_name` → `decisions.gate_name`
- `from_state` / `to_state` → `decisions.from_state` / `decisions.to_state`
- `actor`, `stop_code`, `evidence_refs[]`, `conditions` → `decisions.evidence_json` con chiavi deterministiche:
  - `actor`
  - `stop_code` (solo quando applicabile)
  - `evidence_refs` (lista, anche vuota)
  - `conditions` (lista, anche vuota)
  - `normative_verdict`
- `rationale` → `decisions.rationale` (stringa deterministica, puramente costruita internamente; i gate/CLI non possono fornire input)

`decisions.rationale` è costruita internamente e non accetta stringhe "umane". Qualsiasi spiegazione classificatoria usa `evidence_json.reason_code`; i dettagli diagnostici vanno nei `events`.

### Regole di strictness
- `PASS` / `PASS_WITH_CONDITIONS` richiedono `to_state`.
- `BLOCK` / `FAIL` richiedono `stop_code`.
- `PASS_WITH_CONDITIONS` richiede `conditions` non vuoto.
- `evidence_json` deve essere serializzato in JSON con chiavi ordinate (deterministico).

---

## Evidence Model (Log & Artefact as Evidence)

### Regola generale
- I gate **non validano eventi**.
- I gate validano **affermazioni verificabili**, supportate da evidenze.

### Tipologie di evidenza ammesse
- **Artefatti**: file, directory, database, report QA.
- **Log strutturati**: eventi osservabili, non ambigui, non contraddittori.
- **Segnali di contesto**: es. ledger scrivibile, path-safe, config valida.

Se un'evidenza non è formalizzata:
- il Gatekeeper **deve** indicarlo nel Decision Record (`evidence_gap`).

---

## Predicate di Stato (Beta 1.0 - Normativi)

### `raw_ready`
Stato **attestabile** se e solo se:
- WorkspaceLayout valido e completo.
- Directory canoniche presenti: `raw/`, `config/`, `semantic/`, ledger.
- `config/config.yaml` valido.
- Ledger scrivibile.

**Nota normativa**
- La presenza di PDF **non** definisce lo stato.
- I PDF sono prerequisito per azioni successive, non per lo stato.

---

### `tagging_ready`
Stato **attestabile** se e solo se:
- `semantic/tags.db` esiste ed è coerente.
- `tags_reviewed.yaml` presente (checkpoint HiTL).
- Artefatti semanticamente allineati.

**Predicate unica**
- Questa condizione è unica e non sostituibile.
- Implementazioni multiple devono convergere su questa definizione.

---

## Evidence Gate - Contratto Normativo

L'Evidence Gate:
- valuta **coerenza strutturale e presenza delle evidenze**;
- **non decide avanzamenti**;
- produce sempre un Decision Record.

### Evidence minime per transizione
| Transizione | Evidenze minime richieste |
|------------|---------------------------|
| `WORKSPACE_BOOTSTRAP → SEMANTIC_INGEST` | WorkspaceLayout valido, config valida, ledger scrivibile |
| `SEMANTIC_INGEST → FRONTMATTER_ENRICH` | `semantic/tags.db`, `tags_reviewed.yaml` |
| `FRONTMATTER_ENRICH → VISUALIZATION_REFRESH` | draft markdown + mapping semantico |
| `VISUALIZATION_REFRESH → PREVIEW_READY` | KG + preview artefacts |
| `PREVIEW_READY → COMPLETE` | artefatti finali completi |

---

## Retry / Resume Contract (Beta 1.0)

### Regola fondamentale
**Ogni retry è una nuova run.**

Non esiste:
- retry silenzioso,
- resume implicito,
- "stessa esecuzione".

### Condizioni per retry ammesso
- Artefatti precedenti **ancora integri**.
- Nessuna violazione strutturale (layout, config, scope).
- Nuovo `run_id` e nuovo Decision Record.

### Retry BLOCCATO se
- `WorkspaceLayoutInvalid`
- `WorkspaceNotFound`
- `ConfigError` persistente

In questi casi:
- verdict = `BLOCK`
- `stop_code = HITL_REQUIRED`
- decisione demandata a Timmy (HiTL).

---

## QA Gate ↔ Stato `COMPLETE`

- Il QA Gate è **necessario ma non sufficiente** per completare la pipeline.
- Requisiti minimi QA:
  - `pre-commit run --all-files` → PASS
  - `pre-commit run --hook-stage pre-push --all-files` → PASS
  - report QA disponibili come evidenza
- `logs/qa_passed.json` è il **core-gate artifact** del QA Gate.
- Il campo `timestamp` è telemetria: non entra nel confronto deterministico/manifest dei core artifacts.
- In caso di FAIL: verdict = `BLOCK`, `stop_code = QA_GATE_FAILED`.

Solo dopo:
1. QA Gate produce Decision Record PASS
2. Evidence + Skeptic Gate confermano coerenza finale
3. Timmy/Gatekeeper può attestare `COMPLETE`

La transizione a `COMPLETE` è **essa stessa un Decision Record**.

---

## Non-goals
- Non introduce nuovi stati.
- Non definisce implementazioni o logging dettagliato.
- Non automatizza decisioni: i gate **attestano**, non eseguono.
