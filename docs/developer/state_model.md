# State Model (Beta 1.0)

## Scopo
Questo documento definisce il modello di stato runtime in Beta 1.0.
La fonte di verita e il Decision Ledger: gli stati sotto sono il solo SSoT.

## Definizioni

### Workspace State (stato canonico)
Lo stato del workspace e la proiezione del dato verificabile:
`workspace_state = to_state` dell'ultima decisione `PASS`,
ordinata per `decided_at` e tie-breaker `decision_id`.

### Last Run Status (telemetria / health)
La run piu recente indica la salute operativa (PASS/BLOCK/FAIL), ma non cambia
lo stato canonico del workspace.

## Stati canonici (Decision Ledger SSoT)

| Stato | Significato | Note |
|------|-------------|------|
| `WORKSPACE_BOOTSTRAP` | Workspace inizializzato | layout + config + ledger |
| `SEMANTIC_INGEST` | Workspace attestato per semantica | prerequisiti validati |
| `FRONTMATTER_ENRICH` | Draft frontmatter validata | arricchimento in corso |
| `VISUALIZATION_REFRESH` | Artefatti semantici pronti | KG/preview in coerenza |
| `PREVIEW_READY` | Artefatti finali pronti | QA finale consentita |

### Stati legacy/UX (deprecati)
Le etichette `NEW`, `WORKSPACE_READY`, `TAGS_CSV_READY`, `TAGS_READY`, `SEMANTIC_READY`
non sono SSoT. Possono esistere come descrittori UI, ma non devono comparire nel
Decision Ledger e non guidano le transizioni runtime.

## Transizioni ammesse (Beta 1.0)

### Gate: pre_onboarding
- `WORKSPACE_BOOTSTRAP -> SEMANTIC_INGEST` (PASS/BLOCK/FAIL)

### Gate: normalize_raw (raw_ingest)
- Nessuna transizione di stato: opera intra-state su `WORKSPACE_BOOTSTRAP`.

### Gate: tag_onboarding
- Nessuna transizione di stato: opera intra-state su `SEMANTIC_INGEST`.

### Gate: semantic_onboarding
- `SEMANTIC_INGEST -> FRONTMATTER_ENRICH` (PASS/BLOCK/FAIL)
- `FRONTMATTER_ENRICH -> VISUALIZATION_REFRESH` (PASS/BLOCK/FAIL)
- `VISUALIZATION_REFRESH -> PREVIEW_READY` (PASS/BLOCK/FAIL) se previsto dal gate di preview

## Golden trace (esempio, run OK)
- pre_onboarding: `WORKSPACE_BOOTSTRAP -> SEMANTIC_INGEST` (PASS)
- normalize_raw: `WORKSPACE_BOOTSTRAP -> WORKSPACE_BOOTSTRAP` (PASS)
- tag_onboarding: `SEMANTIC_INGEST -> SEMANTIC_INGEST` (PASS)
- semantic_onboarding: `SEMANTIC_INGEST -> FRONTMATTER_ENRICH` (PASS)
- semantic_onboarding: `FRONTMATTER_ENRICH -> VISUALIZATION_REFRESH` (PASS)
- semantic_onboarding: `VISUALIZATION_REFRESH -> PREVIEW_READY` (PASS)

## Semantica di PASS / BLOCK / FAIL

### PASS
Indica che la transizione e completata e gli artefatti previsti sono persistiti.

### BLOCK / FAIL
Indica un tentativo fallito. `to_state` e il target della transizione, non lo
stato raggiunto.

Regola: lo stato del workspace non avanza mai a causa di un BLOCK/FAIL.

## Policy Strict vs Dummy

### Strict (`TIMMY_BETA_STRICT=1`)
- Blocca la generazione degli stub.
- tag_onboarding resta intra-state su `SEMANTIC_INGEST`.

### Dummy (`--dummy`)
- Abilita eccezionalmente la generazione degli stub end-to-end.
- E ammesso solo se esplicitamente richiesto tramite flag.
- Se strict e attivo, dummy non ha effetto.

### Auditabilita
Quando `--dummy` e usato:
- `evidence_refs` contiene `dummy_mode:true` e `effective_mode:dummy`.
- `rationale` contiene una traccia esplicita (es. `ok_dummy_mode`).

## Derivazione e reporting (ledger-status)
- `current_state` = `workspace_state` (ultimo PASS)
- `gates` = ultima decisione per gate (ordinamento stabile)
- `latest_run` = ultima run (se presente)

## Non previsto (intenzionale, Beta 1.0)
- Motore di inferenza dello stato oltre "latest decision"
- Auto-promotion o fallback silenziosi
