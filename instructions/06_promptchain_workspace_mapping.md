# Prompt Chain ↔ Workspace Mapping (SSoT Binding)
**Status:** ACTIVE
**Scope:** documento di binding unico tra fasi della Prompt Chain, stati workspace e gate richiesti.
**Authority:** questo documento è la fonte SSoT per il binding lifecycle↔workspace↔gate↔event. Le definizioni originarie restano in:
- `instructions/02_prompt_chain_lifecycle.md` (lifecycle e allowed action families)
- `instructions/05_pipeline_workspace_state_machine.md` (stati workspace)
- `instructions/08_gate_evidence_and_retry_contract.md` (Evidence/QA Gate e log richiesti)
- `instructions/07_gate_checklists.md` (checklist operative)

## Cosa definisce vs cosa riferisce
- **Definisce:** mapping tra fasi e stati, gate richiesti per transizioni, binding gate→event, bridge fields minimi.
- **Riferisce:** semantica di fasi/stati/gate dai documenti sopra; nessuna reinterpretazione.

## Out of scope
- Nessuna modifica a fasi, stati, gate o action families.
- Nessuna definizione di nuovi eventi oltre ai binding qui indicati.
- Nessun requisito di implementazione o log emission; solo vincoli di binding.

## Lifecycle phases → Workspace states → Allowed action families
Riferimenti: `instructions/02_prompt_chain_lifecycle.md`, `instructions/05_pipeline_workspace_state_machine.md`.

| Lifecycle phase | Workspace state(s) | Allowed action families |
|---|---|---|
| PLANNING | bootstrap (derived) | `REGISTER_*` |
| MICRO_PLANNING | bootstrap (derived) | definizione Work Order Envelope |
| VALIDATION | raw_ready, tagging_ready | `VALIDATE_*` |
| EXECUTION | pronto, arricchito | `GENERATE_*`, `EXECUTE_*` |
| QA | arricchito → finito | `VALIDATE_*` |
| CLOSURE | finito | summary logging / closure |

## Gate requirements per transizione workspace
Riferimenti: `instructions/08_gate_evidence_and_retry_contract.md`, `instructions/07_gate_checklists.md`.

| Transizione workspace | Gate richiesti |
|---|---|
| bootstrap → raw_ready | Evidence Gate + Skeptic Gate |
| raw_ready → tagging_ready | Evidence Gate + Skeptic Gate |
| tagging_ready → pronto | Evidence Gate + Skeptic Gate |
| pronto → arricchito | Evidence Gate + Skeptic Gate |
| arricchito → finito | QA Gate + Evidence Gate + Skeptic Gate |
| finito → out-of-scope | QA Gate finale + Skeptic Gate |

## Gate → Event binding (Decision Record)
Riferimento: `instructions/08_gate_evidence_and_retry_contract.md` (evidence log-based).

| Gate | Evento canonico obbligatorio | Emissione |
|---|---|---|
| Evidence Gate | `evidence_gate_blocked` | SOLO su BLOCK/STOP |
| Skeptic Gate | `skeptic_gate_blocked` / `skeptic_gate_pass_with_conditions` | SOLO su BLOCK o PASS WITH CONDITIONS |
| QA Gate | `qa_gate_failed` / `qa_gate_retry` | SOLO su FAIL/RETRY |

## Bridge fields minimi (lifecycle ↔ workspace)
Riferimenti: `instructions/04_microagents_work_orders.md`, `docs/observability.md`, `system/ops/runbook_codex.md`.

| Campo | Obbligatorietà | Note |
|---|---|---|
| `run_id` | sempre | obbligatorio per correlazione run |
| `slug` | sempre | workspace identifier |
| `phase_id` | sempre | lifecycle phase corrente |
| `state_id` | sempre | workspace state corrente |
| `intent_id` | sempre | registro Intent/Action |
| `action_id` | sempre | azione eseguita |
| `trace_id` | solo se OTEL attivo | obbligatorio quando OTEL è abilitato |
| `span_id` | solo se OTEL attivo | obbligatorio quando OTEL è abilitato |
