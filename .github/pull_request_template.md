## Scopo
<!-- Breve descrizione del cambiamento e del perché -->

## Scope
- [ ] Tipo PR: bugfix / feature / refactor / docs / tooling
- [ ] Area: retriever / pipeline / semantic / ui / ai / security / storage / other
- [ ] Questa PR è una micro-PR con scope limitato e reversibile

## Checklist tecnica (bloccante)
- [ ] Rispetto **Coding Rules** (typing, logger strutturato, **no `print()`**)
      <!-- vedi docs/developer/coding_rule.md -->
- [ ] Path-safety & scritture **atomiche** dove si scrive su filesystem
- [ ] Nessun side-effect a import-time nei moduli runtime
- [ ] Doc aggiornate (README / docs/* / system/*) e CHANGELOG aggiornato se necessario
      **(blocking)** - indica in descrizione `Docs: ...`
- [ ] Test/coverage ok (`pytest`) e type-check ok (`mypy`)
- [ ] QA locale eseguita:
  - [ ] `pre-commit run --all-files`
  - [ ] `pytest -q`
  - [ ] (se intermedio) `pytest -q -k "not slow"`
- [ ] Nessun push forzato
      oppure `--force-with-lease` + allow-list + `force_ack`
      <!-- governance push -->

---

## Beta DoD - Determinismo & Low Entropy

### Contratto di osservabilità (retriever.*)
Se questa PR tocca **direttamente o indirettamente** il retriever:

- [ ] `retriever.query.started` resta correlabile (include `response_id` e campi base).
- [ ] `retriever.candidates.fetched` include `budget_hit` e contatori (`candidate_limit`, `candidates_loaded`, `ms`).
- [ ] Se il retriever ritorna `[]`, esiste **almeno un evento disambiguante** tra:
  - [ ] `retriever.throttle.deadline` (preflight)
  - [ ] `retriever.latency_budget.hit` (embedding / fetch)
  - [ ] `retriever.query.embed_failed` (errore embedding gestito)
  - [ ] `retriever.query.invalid` / `retriever.query.skipped`
- [ ] Nessuna degradazione silenziosa: ogni STOP / short-circuit produce un evento loggato.

### Contratto semantico
- [ ] La PR **non introduce** nuovi casi in cui:
  - "no match"
  - "errore gestito"
  - "budget/deadline"

  collassano nello stesso comportamento **senza evento disambiguante**.

---

## Docs
<!-- Elenca i file aggiornati o scrivi `n/a` solo se non necessari -->
Docs:

Branch protection & required checks:
vedi `docs/security.md` - CI / Secret Scan **devono essere verdi** prima del merge.

---

## QA eseguita e risultati
- [ ] `pre-commit run --all-files`
- [ ] `pytest -q`
- [ ] `pytest -q -k "not slow"` (se applicabile)

---

## Skeptic Gate
- **Evidence** (link, log, diff, screenshot):
- **Scope escluso** (cosa NON è stato toccato):
- **Rischi residui / ambiguità note**:
- **Decisione**: PASS / PASS WITH CONDITIONS / BLOCK

---

## Waiver (solo se necessario)
Se questa PR **non rispetta completamente il DoD Beta**, specificare:
- Motivo della deroga:
- Impatto noto:
- Evidenza che la degradazione NON è silenziosa (evento/log):
- Issue di tracciamento:

---

## Note HiTL
- Reviewer:
- Domande aperte:
- Cosa verificare prima del merge:
