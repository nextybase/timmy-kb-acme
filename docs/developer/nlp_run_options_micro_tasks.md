# NLP Run Options - Micro Tasks Operativi

Riferimento: `docs/developer/nlp_run_options_cleanup_plan.md`

## MT-1 - Telemetria deprecazione e baseline adozione

Scope:
- raccogliere evidenza sull'uso reale dei parametri legacy (`rebuild`, `only_missing`, `max_workers`, `worker_batch_size`, `enable_entities`)
- confermare che l'evento `cli.tag_onboarding.nlp_legacy_kwargs_deprecated` sia tracciabile nei log operativi

Output atteso:
- nota tecnica con conteggio occorrenze (finestra temporale definita)
- decisione go/no-go per lo switch T2

QA minima:
- verifica presenza evento nei log
- verifica campi `legacy_fields` e `precedence`

Stima impatto:
- 20-40 minuti

## MT-2 - Switch API typed-only (T2)

Scope:
- rimuovere dalla signature di `run_nlp_to_db` i parametri legacy
- mantenere solo `options: NlpRunOptions`
- eliminare logica `legacy_overrides` e warning di deprecazione

Output atteso:
- API unificata e non ambigua
- call-site interni allineati al contratto typed

QA minima:
- `pre-commit run --all-files`
- `python -m pytest -q`
- test esplicito: chiamata legacy deve fallire con `TypeError`

Stima impatto:
- 30-60 minuti

## MT-3 - Pulizia post-switch e guardrail anti-regressione (T3)

Scope:
- rimuovere test/protezioni transitorie non piu necessarie
- aggiungere guardrail che impedisca reintroduzione dei parametri legacy nei call-site interni

Output atteso:
- codebase semplificata
- regressioni prevenute da test statici/dinamici

QA minima:
- `pre-commit run --all-files`
- `python -m pytest -q`
- check grep in CI sui parametri legacy nella chiamata a `run_nlp_to_db`

Stima impatto:
- 20-40 minuti

## Sequenza consigliata

1. MT-1
2. MT-2
3. MT-3
