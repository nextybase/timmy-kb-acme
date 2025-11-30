# Observability Stack

Questa guida completa la documentazione di logging già integrata nel progetto
(`observability/docker-compose.yaml`, `observability/promtail-config.yaml`).

## Stack base (Loki + Promtail + Grafana)

1. Avvia gli stack locali (usando il `.env` in root):
   ```bash
   docker compose --env-file ./.env -f observability/docker-compose.yaml up -d
   ```
2. I log applicativi vengono raccolti da Promtail e inviati a Loki.
3. Grafana espone la dashboard (default: <http://localhost:3000>).
   La password admin è letta da `GRAFANA_ADMIN_PASSWORD` nel `.env` in root;
   se assente, parte con `admin` (fallback del compose).

I file di log raccolti includono sia i workspace (`/var/timmy/output/timmy-kb-*/logs/*.log`)
sia i log globali (`/var/timmy/global-logs/*.log`). Le pipeline di Promtail
promuovono come label principali:

 - `event`
 - `slug`
  - `run_id`
  - `ui.semantics.*` eventi di gating (`ui.semantics.gating_blocked` / `ui.semantics.gating_allowed`) utili per verificare lo stato RAW e i percorsi.

> Nota: le stage `replace` nel file `promtail-config.yaml` oscurano automaticamente
> header sensibili (`Authorization`, `x-access-token`).

### Provisioning Grafana

- Le configurazioni vengono caricate da `observability/grafana-provisioning/`:
  - `datasources/` definisce la sorgente Loki (UID `Loki`).
  - `alerting/` contiene le regole (`TimmyKB Alerts`).
  - `dashboards/` punta alla directory montata `/var/lib/grafana/dashboards`.
- Le dashboard JSON risiedono in `observability/grafana-dashboards/`
  e vengono montate in sola lettura; usa `grafana-toolkit export` o copia manuale
  per aggiornarle, poi committa il JSON.
- Puoi valorizzarle nel `.env` in root:
  ```
  GRAFANA_ADMIN_USER=observability-admin
  GRAFANA_ADMIN_PASSWORD=<strong-password-here>
  ```

## Correlazione tracing (`trace_id` / `span_id`)

`pipeline/logging_utils.py` integra opzionalmente OpenTelemetry. Se abiliti
l'endpoint OTLP:

```bash
export TIMMY_OTEL_ENDPOINT="http://localhost:4318/v1/traces"
export TIMMY_SERVICE_NAME="timmy-kb"
export TIMMY_ENV="production"
```

L'applicazione manda gli span all'OTEL Collector locale (`TIMMY_OTEL_ENDPOINT`)
che inoltra i dati a Tempo via OTLP gRPC. Nei log compariranno i campi
`trace_id` e `span_id`; Grafana sfrutta il datasource Tempo e la feature
`tracesToLogs` per seguire la catena trace ↔ log (grazie ai label `slug`,
`run_id`, `phase`, `event`). Quando usi `pipeline.logging_utils.phase_scope`, i
log emettono automaticamente gli stessi ID se `TIMMY_OTEL_ENDPOINT` è impostato.

Puoi verificare il collegamento aprendo una trace view in Grafana (top right
“View logs / View trace”), scegliere il trace e cliccare la lente “View logs”
per aprire Loki con i filtri `trace_id`, `slug`, `run_id`. Se tutto è configurato
correttamente vedrai la sezione log associata e potrai scorrere sia lo span che
le righe log correlate (anche da un altro pannello se usi la dashboard dedicata).

## Query utili (Grafana / Loki)

- Tutti gli errori di fase fallita:
  ```logql
  {job="timmy-kb", event="phase_failed"}
  ```
- Log per un determinato cliente con riferimento al retriever:
  ```logql
  {slug="acme"} |~ "semantic.index"
  ```
- Traccia con correlazione OTEL (se attiva):
  ```logql
  {trace_id="0123456789abcdef0123456789abcdef"}  # pragma: allowlist secret
  ```

## Dashboard predefinito Timmy

- `TIMMY_GRAFANA_LOGS_UID`: UID della dashboard Grafana dedicata ai log di run (`observability/grafana-dashboards/logs-dashboard.json`). Il pannello *Log dashboard* (UI) aggiunge un pulsante per aprire la dashboard log filtrata sullo `slug` attivo (`var-slug`) e il datasource della dashboard punta a Loki (`Loki`).
- `TIMMY_GRAFANA_ERRORS_UID`: UID della dashboard Grafana focalizzata su errori per fase (`observability/grafana-dashboards/errors-dashboard.json`). Il pulsante “Apri dashboard errori” apre questa dashboard con filtro `slug`/`phase` e la query Loki `level="ERROR"` per fase.

### Indicatori di stack

- La UI mostra un badge `Grafana 🟢/🔴` nella sezione osservabilità e lo aggiorna solo se Docker è attivo, così distingui subito se lo stack è raggiungibile o meno.
- Se Docker non è attivo, compare un messaggio informativo con il comando `{docker compose ... up -d}` da eseguire prima di usare i pulsanti; Start/Stop restano disabilitati fino a quel momento.
- Quando Docker è disponibile, i pulsanti `Start Stack` e `Stop Stack` invocano internamente le funzioni esposte in `scripts/observability_stack.py` per lanciare `docker compose up -d` o `docker compose down`. Se tutto va a buon fine la UI mostra un messaggio di conferma (`Stack avviato: …` / `Stack fermato: …`), altrimenti riporta un warning con l’errore.

I valori vengono letti in tempo reale e non ci sono side effect: basta aggiornare `.env` (o i `TIMMY_*` dei container) e riavviare l’interfaccia.

### Helper CLI (scripts/observability_stack)

Lo stesso helper `scripts/observability_stack.py` è disponibile anche come script stand-alone per chi preferisce avviare/fermare lo stack da shell. Esegui il comando

```bash
python scripts/observability_stack.py start
```

per avviare l’intero stack e

```bash
python scripts/observability_stack.py stop
```

per fermarlo; lo script stampa l’output del `docker compose` e restituisce exit code `0` solo in caso di successo.

Le opzioni `--env-file` / `--compose-file` permettono di sovrascrivere rispettivamente `TIMMY_OBSERVABILITY_ENV_FILE` e `TIMMY_OBSERVABILITY_COMPOSE_FILE` (default `.env` e `observability/docker-compose.yaml`), quindi la UI e lo script condividono la stessa configurazione runtime.

### Span OTEL e attributi

La nuova telemetria OTEL è composta da:

- **Trace root** (`timmykb.<journey>`, es. `timmykb.onboarding`, `timmykb.ingest`, `timmykb.reindex`)
  - Attributi: `slug`, `run_id`, `trace_kind`, `env`, `entry_point`, `journey`
- **Phase span** (`phase:<phase>`, aperto da `phase_scope`)
  - Attributi: `phase`, `slug`, `run_id`, `trace_kind`, `status`, `artifact_count`, `dataset_area`, `source_type`, `policy_id`, `petrov_action`, `rosetta_quality_score`, `risk_level`, `error_kind`, `error_code`
- **Decision span** (`decision:<decision_type>` per filtri/semantica/override umano)
  - Attributi: `decision_type`, `slug`, `run_id`, `trace_kind`, `phase`, `reason`, `policy_id`, `dataset_area`, `er_entity_type`, `er_relation_type`, `model_version`, `ambiguity_score`, `hilt_involved`, `user_role`, `override_reason`, `previous_value`, `new_value`, `status`

Grafana sfrutta `trace_id`, `span_id`, `slug`, `run_id`, `phase` e `decision_type` per incatenare trace e log nelle dashboard dedicate.

### Human override spans

Ogni volta che l'amministratore UI salva/rigenera `tags_reviewed.yaml` (sia in modalità stub che con il servizio `tags_adapter`), il codice chiama `start_decision_span` con `decision_type=human_override` e `phase=ui.manage.tags_yaml`. Gli span portano sempre:

- `slug`, `run_id`, `trace_kind=onboarding` per trovare la trace primaria.
- `override_reason` (`manual_publish`, `state_override`, `manual_tags_csv`, `stub_publish`) e l'indicazione di `hilt_involved=true` / `user_role` per ricostruire chi ha preso la decisione.
- `previous_value` / `new_value` per mostrare il cambio di stato (`pronto` → `arricchito`).
- `status` (`success` / `failed`) e `reason` per capire se la modifica ha avuto effetto.

Per ogni cambio di stato (nell'helper `set_client_state`) tracciamo anche un micro-span dedicato con `attributes={"previous_value": ..., "new_value": ...}`: ciò rende possibile, in Grafana, seguire la catena `trace_root → phase_span → decision_span → log (ui.manage.state.update_failed)` e ricostruire ogni decisione umana sul dataset.

### Fallback e resilienza semantica

- `semantic.api.build_tags_csv` valida ora che `tags.db` derivato risieda sotto `semantic/` prima di arricchire il vocabolario e scrivere su SQLite, mantenendo il requisito path-safety descritto nelle regole.
- Se `storage.tags_store.load_tags_reviewed` non è disponibile (es. ambienti di test minimal), l’evento `semantic.vocab_loader.stubbed` viene loggato immediatamente con l’errore, rendendo visibile il downgrade e permettendo la correzione prima di una fail-fast.
- `_compute_embeddings_for_markdown` ora cattura gli errori dal provider embedding, logga `semantic.index.embedding_error` e restituisce `(None, 0)` invece di propagare un’eccezione: la trace `index_markdown_to_db` rimane leggibile (phase span completo) e la pipeline può continuare gestendo il fallback nei log successivi.

### Decision span sampling

- La variabile d’ambiente `TIMMY_DECISION_SPAN_SAMPLING` (default `1.0`) controlla quanti micro-span vengono davvero emessi per gli eventi decisionali. Impostando valori più bassi (es. `0.1`) limitiamo la quantità di span in Tempo mantenendo comunque i log completi in Loki. Il sampling avviene solo sui span decisionali; se un trace è attivo ma il campionamento scarta lo span, i log contenenti `trace_id`/`span_id` rimangono intatti per la correlazione.

### Tracing doctor

- Il pannello Log UI aggiunge ora un pulsante “Verifica tracing” che emette un `trace_kind=diagnostic` / `phase=observability.tracing.doctor` con un log `observability.tracing.test_span_emitted`. Dopo aver premuto il pulsante puoi aprire Tempo, filtrare per `trace_kind=diagnostic` e controllare che il Collector riceva davvero gli span generati da l’interfaccia.

## Alerting critico

## Alerting critico

Per inviare alert in tempo reale (es. Slack, Sentry):

- configura Promtail/Loki con alert rules oppure
- imposta un ricevitore (es. Sentry) usando il bridge OpenTelemetry.

Assicurati che eventuali token generati in GitHub Actions siano mascherati (`::add-mask::`)
prima di venire stampati nei log.

## Buone pratiche

- Evita di loggare variabili di ambiente o payload contenenti segreti.
- Usa `pipeline/logging_utils.get_structured_logger` per tutti i logger.
- Mantieni attivi i filtri di redazione e aggiorna `promtail-config.yaml`
  con pattern ulteriori qualora emergano nuovi tipi di credenziali.
