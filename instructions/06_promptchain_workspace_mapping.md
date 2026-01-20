# Prompt Chain ↔ Workspace Mapping (SSoT Binding)

**Status:** ACTIVE
**Authority:** Single Source of Truth (SSoT)
**Scope:** binding normativo tra lifecycle della Prompt Chain, stati del workspace,
gate richiesti e Decision Record.

Questo documento **non introduce semantica nuova**:
vincola e rende coerenti definizioni già presenti nei documenti sorgente.

Fonti normative:
- `instructions/02_prompt_chain_lifecycle.md` - lifecycle e action families
- `instructions/05_pipeline_state_machine.md` - stati workspace
- `instructions/07_gate_checklists.md` - checklist operative dei gate
- `instructions/08_gate_evidence_and_retry_contract.md` - Evidence / QA / Skeptic Gate

Se esiste un conflitto, **prevale questo documento** come binding SSoT.

---

## Cosa definisce vs cosa riferisce

### Definisce
- Mapping **lifecycle phase ↔ workspace state**.
- Gate **obbligatori** per ogni transizione di stato.
- Vincolo **Gate → Decision Record** (append-only).
- Bridge fields minimi per correlazione lifecycle / workspace / gate.

### Riferisce
- Semantica delle fasi lifecycle.
- Semantica degli stati workspace.
- Regole interne dei gate.
- Policy di retry e stop.

---

## Out of Scope
- Introduzione di nuovi stati, fasi o gate.
- Modifica delle action families.
- Definizione di implementazione, logging o strumenti.
- Introduzione di eventi alternativi o shortcut semantici.

---

## Lifecycle phases → Workspace states → Allowed action families

Riferimenti:
- `instructions/02_prompt_chain_lifecycle.md`
- `instructions/05_pipeline_state_machine.md`

| Lifecycle phase | Workspace state(s) ammessi | Allowed action families |
|-----------------|----------------------------|--------------------------|
| PLANNING | `WORKSPACE_BOOTSTRAP` | `REGISTER_*` |
| MICRO_PLANNING | `WORKSPACE_BOOTSTRAP` | definizione Work Order Envelope |
| VALIDATION | `SEMANTIC_INGEST`, `FRONTMATTER_ENRICH` | `VALIDATE_*` |
| EXECUTION | `FRONTMATTER_ENRICH`, `VISUALIZATION_REFRESH` | `GENERATE_*`, `EXECUTE_*` |
| QA | `VISUALIZATION_REFRESH`, `PREVIEW_READY` | `VALIDATE_*` |
| CLOSURE | `PREVIEW_READY` | summary logging / closure |

**Nota normativa**
- Le lifecycle phases **non avanzano** lo stato del workspace.
- Le lifecycle phases governano il *processo decisionale*, non l'attestazione.

---

## Gate requirements per transizione workspace

Riferimenti:
- `instructions/07_gate_checklists.md`
- `instructions/08_gate_evidence_and_retry_contract.md`

| Transizione workspace | Gate richiesti (tutti obbligatori) |
|-----------------------|------------------------------------|
| `WORKSPACE_BOOTSTRAP → SEMANTIC_INGEST` | Evidence Gate + Skeptic Gate |
| `SEMANTIC_INGEST → FRONTMATTER_ENRICH` | Evidence Gate + Skeptic Gate |
| `FRONTMATTER_ENRICH → VISUALIZATION_REFRESH` | Evidence Gate + Skeptic Gate |
| `VISUALIZATION_REFRESH → PREVIEW_READY` | Evidence Gate + Skeptic Gate |
| `PREVIEW_READY → COMPLETE` | QA Gate + Evidence Gate + Skeptic Gate |

Nessuna transizione è valida se **anche uno solo** dei gate richiesti non emette verdict.

---

## Gate → Decision Record binding (Beta 1.0)

Riferimento:
- `instructions/08_gate_evidence_and_retry_contract.md`

### Regola fondamentale
**Ogni transizione di stato produce sempre un Decision Record append-only.**
Non esistono transizioni "silenziose".

| Gate | Verdict ammessi | Output normativo |
|-----|-----------------|------------------|
| Evidence Gate | `PASS`, `BLOCK`, `FAIL` | Decision Record |
| Skeptic Gate | `PASS`, `PASS_WITH_CONDITIONS`, `BLOCK` | Decision Record |
| QA Gate | `PASS`, `FAIL`, `RETRY` | Decision Record |

Eventi specifici (`*_blocked`, `*_retry`, ecc.) possono esistere come **log o telemetria**,
ma **non sostituiscono** mai il Decision Record.

---

## Bridge fields minimi (lifecycle ↔ workspace ↔ gate)

Riferimenti:
- `instructions/04_microagents_work_orders.md`
- `docs/observability.md`
- `system/ops/runbook_codex.md`

| Campo | Obbligatorio | Note normative |
|------|--------------|----------------|
| `run_id` | sempre | Identificatore univoco della run |
| `slug` | sempre | Workspace identifier |
| `phase_id` | sempre | Lifecycle phase corrente |
| `state_id` | sempre | Workspace state corrente |
| `intent_id` | sempre | Registro Intent/Action |
| `action_id` | sempre | Azione eseguita |
| `decision_id` | sempre | Identificatore Decision Record |
| `trace_id` | se OTEL attivo | Obbligatorio se OTEL abilitato |
| `span_id` | se OTEL attivo | Obbligatorio se OTEL abilitato |

---

## Invarianti anti-confusione
- **Lifecycle ≠ Pipeline**
  Il lifecycle governa il *ragionamento*, la pipeline governa lo *stato*.
- **Artefact readiness ≠ stato**
  Gli artefatti sono evidenze, non decisioni.
- **Gate ≠ automatismo**
  I gate producono verdict, non avanzamenti impliciti.
- **Decision Record = verità**
  Se non esiste un Decision Record, la transizione **non è avvenuta**.
