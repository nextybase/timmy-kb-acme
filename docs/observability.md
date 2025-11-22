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
export TIMMY_OTEL_ENDPOINT="https://otel-collector.example.com/v1/traces"
export TIMMY_SERVICE_NAME="timmy-kb"
export TIMMY_ENV="production"
```

All'interno dei log compariranno i campi `trace_id` e `span_id`. Questi campi
possono essere usati in Grafana o in altri back-end OTEL per risalire
all'esecuzione correlata.
Quando usi `pipeline.logging_utils.phase_scope`, i log emettono automaticamente gli stessi ID se `TIMMY_OTEL_ENDPOINT` è impostato.

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

- `TIMMY_GRAFANA_LOGS_UID`: UID della dashboard Grafana dedicata ai log Timmy.
  Se la variabile è valorizzata, il pannello *Log dashboard* (UI) aggiunge un pulsante per aprire la dashboard log filtrata sullo `slug` attivo (`var-slug`).
- `TIMMY_GRAFANA_ERRORS_UID`: UID della dashboard Grafana con errori/alert Timmy.
  Anche questa dashboard viene collegata direttamente dal pannello Log quando la variabile è presente; se è definito anche lo `slug`, il link contiene `?var-slug=<slug>` per filtrare per cliente.

### Indicatori di stack

- La UI mostra un badge `Grafana 🟢/🔴` nella sezione osservabilità e lo aggiorna solo se Docker è attivo, così distingui subito se lo stack è raggiungibile o meno.
- Se Docker non è attivo, compare un messaggio informativo con il comando `{docker compose ... up -d}` da eseguire prima di usare i pulsanti; Start/Stop rimangono nascosti fino a quel momento.
- Quando Docker è disponibile, appaiono due pulsanti: `Start Stack` (quando Grafana non risponde) e `Stop Stack` (quando è online); premendoli l’interfaccia mostra il comando da eseguire (`up -d` o `down`) ma l’azione resta manuale.

I valori vengono letti in tempo reale e non ci sono side effect: basta aggiornare `.env` (o i `TIMMY_*` dei container) e riavviare l’interfaccia.

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
