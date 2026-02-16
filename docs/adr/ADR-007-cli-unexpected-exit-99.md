# ADR-007 - CLI Unexpected Exit Code = 99 (Firewall Epistemico)

**Status:** Accepted (Beta 1.0)

## Contesto

Timmy KB utilizza diverse CLI core per l'esecuzione di processi automatici
(onboarding, ingestion, QA, build).

In precedenza, eccezioni non tipizzate (bug, errori inattesi, incoerenze runtime)
potevano essere:

- mascherate come `PipelineError` (exit code `1`)
- normalizzate da catch-all generici
- propagate come traceback non governati

Questo introduceva entropia semantica e riduceva auditabilita operativa.

## Decisione

A partire dalla Beta 1.0, il contratto di terminazione processo e deterministico:

- `0` = Success
- `2` = ConfigError
- `1` = PipelineError (errore previsto di dominio)
- `99` = UnexpectedError (fuori contratto)
- `130` = KeyboardInterrupt

Qualsiasi eccezione non esplicitamente mappata e trattata come `UnexpectedError`
e produce exit code `99`.

## Runner come Firewall Epistemico

Il wrapper `run_cli_orchestrator()` mantiene un catch-all intenzionale:

- non e fallback
- non e retrocompatibilita
- e enforcement contrattuale

Serve a garantire che nessuna CLI core produca traceback non governati
in ambienti automatici.

## Alternative considerate

### Rimozione del catch-all

Scartata per Beta 1.0:

- aumenta fragilita operativa
- non aggiunge determinismo oltre a `unexpected=99`
- peggiora UX in ambienti dedicati

## Conseguenze

- Semantica uniforme degli errori inattesi
- Maggiore auditabilita nei supervisor di processo
- Eliminazione di shim `Exception -> PipelineError`
- Guardrail tramite contract tests

## Riferimenti

- Commit: `fix(cli): enforce unexpected exit code 99 and add contract guardrail`
