# QA Gate Policy (CORE-GATE)

## Cos'è `qa_passed.json`
`qa_passed.json` è l'evidenza strutturata del QA Gate, scritta in:
`output/timmy-kb-<slug>/logs/qa_passed.json`.

## Perché è CORE-GATE
È un prerequisito normativo per generare i core artifacts di `book/`
(`README.md`, `SUMMARY.md`). Se manca o è invalido, il gate blocca.

## Campi normativi vs telemetria

**Normativi (usati per il gate):**
- `schema_version`
- `qa_status` (`pass`/`fail`)
- `checks_executed` (lista non vuota)

**Telemetria (non deterministica):**
- `timestamp` (wall-clock; non entra nel confronto deterministico/manifest)
