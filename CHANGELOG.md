# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue *Keep a Changelog* e *Semantic Versioning*.

## TODO (prioritaria): Stabilizzare i workflow `pip-audit` (Dependency Scan / Security Audit)

### Contesto
Nel repository sono presenti più workflow e configurazioni che usano `pip-audit` (es. `.github/workflows/security-audit.yml`, `.pre-commit-config.yaml`, documentazione di security). In CI il check “Dependency Scan/pip-audit (pull_request)” risulta fallire.

### Errore osservato (CI)
Nel job `pip-audit` su GitHub Actions, durante lo step di esecuzione del comando, l’esecuzione termina con errore di parsing dei parametri:

- Comando lanciato:
  - `pip-audit -r requirements.txt -r requirements-dev.txt --progress-spinner off --format sarif`
- Output rilevante:
  - `pip-audit: error: argument -f/--format: invalid OutputFormatChoice value: 'sarif'`
- Esito:
  - `Process completed with exit code 2`

Quindi il fallimento non deriva (almeno in questo run) da vulnerabilità trovate, ma da un argomento CLI non accettato dalla versione effettivamente installata/eseguita in CI.

### Sintomi correlati / segnali utili
- Nel log si vede che in CI viene installata una versione di `pip-audit` differente da quella attesa/standardizzata altrove nel repo (es. in file di dipendenze e hook è presente un pin a `pip-audit==2.7.2`, ma nel run CI viene installato un pacchetto `pip-audit` che risulta poi essere `2.10.0`).
- Il comando che fallisce usa `--format sarif`, mentre in altre parti del repository si fa riferimento anche a output JSON e a logiche che leggono `pip-audit.json` e calcolano severità via `jq` (quindi coesistono formati/percorsi differenti).
- Questo crea una discrepanza tra:
  1) formato richiesto dal comando (SARIF),
  2) formato effettivamente supportato dalla versione in esecuzione,
  3) formato e file attesi dagli step successivi (es. `pip-audit.json` o output JSON).

### Punti da controllare (solo verifica, nessuna azione implicita)
1. **Versione effettiva di `pip-audit` in CI**: confermare quale versione viene installata/risolta nel workflow che fallisce e se corrisponde a quella prevista nel repo.
2. **Coerenza tra workflow**: verificare che `security-audit.yml` (ora `Dependency Audit (pip-audit)`) rispetti le opzioni CLI, i formati e i gate previsti per `pip-audit`.
3. **Supporto formati**: verificare, per la versione effettiva usata nel job, quali valori sono accettati da `-f/--format` e se `sarif` è incluso tra questi.
4. **Output atteso a valle**: controllare quali step (o integrazioni) assumono l’esistenza di un file JSON (`pip-audit.json`) e come viene gestita l’assenza/empty file.
5. **Allineamento con pre-commit e requirements**: verificare che `requirements-dev.*` e `.pre-commit-config.yaml` non impongano aspettative diverse (versione e comportamento) rispetto ai workflow CI.
6. **Ambiente runner**: annotare OS e Python della GitHub runner usata nei run falliti (Ubuntu 24.04.x, Python 3.11.x), nel caso il comportamento sia influenzato da packaging/risoluzione dipendenze.

### Impatto
- Il check PR “Dependency Scan/pip-audit” fallisce per errore di invocazione CLI, bloccando la pipeline (o comunque segnando la PR come non green) anche senza evidenza di vulnerabilità.


TODO (pre-1.0 Beta): audit duplicazione test (post-normalizzazione)
- Avviare audit mirato sui test non-skippati con alta densità (es. area `tests/ai/`, `tests/semantic/`, `tests/retriever*`) per individuare duplicazioni reali o near-duplicazioni.
- Distinguere tra:
  - duplicazioni nocive (stesso contratto testato più volte senza valore aggiunto),
  - duplicazioni utili (stesso shape ma casi/parametri diversi),
  - duplicazioni cross-layer (stesso contratto testato in layer differenti).
- Escludere esplicitamente dall'audit i test UI sempre skippati (policy Beta 1.0) o trattarli in sezione separata.
- Definire una strategia di consolidamento (test canonico + parametrizzazione / riallocazione di livello) evitando over-engineering.


TODO: realizzare completamente l'agent builder come definito in `instructions/14_agent_package_contract.md`.

TODO (pre-1.0 Beta): revisione logging/observability - creazione/gestione dashboard, standardizzare messaggi, separare log operativi/artefatti normativi e minimizzare entropia prima del rilascio finale. Non blocca i fix correnti.
