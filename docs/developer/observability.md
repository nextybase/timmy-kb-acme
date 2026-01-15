# Observability Stack (Beta 1.0)

Questa guida completa la documentazione di logging già integrata nel progetto
(`observability/docker-compose.yaml`, `observability/promtail-config.yaml`).

Per Beta 1.0 valgono invarianti di governance:
- nessun “best-effort” silenzioso;
- nessun fallback implicito;
- ogni degrado operativo deve essere **esplicito, osservabile e bloccante** quando impatta la qualità/completezza degli artefatti.

---

## Stack base (Loki + Promtail + Grafana)

1. Avvia lo stack locale (usando il `.env` in root):
   ```bash
   docker compose --env-file ./.env -f observability/docker-compose.yaml up -d
   ```
2. I log applicativi vengono raccolti da Promtail e inviati a Loki.
3. Grafana espone la dashboard (default: <http://localhost:3000>).

### Credenziali Grafana (policy Beta 1.0)
- La password admin deve essere definita in `.env` tramite `GRAFANA_ADMIN_PASSWORD`.
- Se `GRAFANA_ADMIN_PASSWORD` è assente:
  - lo stack può avviarsi a livello Docker (comportamento del compose),
  - ma il sistema è **non conforme** e va trattato come **misconfiguration**.
- In modalità Beta 1.0, l’assenza di password configurata deve produrre:
  - un warning esplicito in UI/CLI (“observability.misconfig.grafana_password_missing”),
  - e deve bloccare l’abilitazione dei pulsanti dashboard se usati come strumenti operativi.

I file di log raccolti includono sia i workspace (`/var/timmy/output/timmy-kb-*/logs/*.log`)
sia i log globali (`/var/timmy/global-logs/*.log`).

Le pipeline di Promtail promuovono come label principali:
- `event`
- `slug`
- `run_id`

Eventi utili:
- `ui.semantics.*` eventi di gating (`ui.semantics.gating_blocked` / `ui.semantics.gating_allowed`)
- `run_id` viene estratto anche dai log UI globali (`.timmy_kb/logs/ui.log`) generati da l’entrypoint Streamlit.
- Se OTEL è attivo compaiono anche `trace_id`/`span_id` nel log (non come label) e possono essere usati in Grafana per correlazione trace/log.

> Nota: le stage `replace` in `promtail-config.yaml` oscurano automaticamente
> header sensibili (`Authorization`, `x-access-token`).
> È prevista anche la redazione di `SERVICE_ACCOUNT_FILE` per i percorsi credenziali.

---

## Provisioning Grafana

- Le configurazioni vengono caricate da `observability/grafana-provisioning/`:
  - `datasources/` definisce la sorgente Loki (UID `Loki`).
  - `alerting/` contiene le regole (`Timmy KB Alerts`).
  - `dashboards/` punta alla directory montata `/var/lib/grafana/dashboards`.
- Le dashboard JSON risiedono in `observability/grafana-dashboards/`
  e vengono montate in sola lettura; usa `grafana-toolkit export` o copia manuale
  per aggiornarle, poi committa il JSON.
- Variabili suggerite in `.env`:
  ```
  GRAFANA_ADMIN_USER=observability-admin
  GRAFANA_ADMIN_PASSWORD=<strong-password-here>
  ```

---

## Correlazione tracing (`trace_id` / `span_id`)

`pipeline/logging_utils.py` integra opzionalmente OpenTelemetry. Se abiliti
l’endpoint OTLP:

```bash
export TIMMY_OTEL_ENDPOINT="http://localhost:4318/v1/traces"
export TIMMY_SERVICE_NAME="timmy-kb"
export TIMMY_ENV="production"
```

L’applicazione manda gli span all’OTEL Collector locale (`TIMMY_OTEL_ENDPOINT`)
che inoltra i dati a Tempo via OTLP gRPC. Nei log compariranno i campi
`trace_id` e `span_id`; Grafana sfrutta il datasource Tempo e la feature
`tracesToLogs` per seguire la catena trace → log (grazie ai label `slug`,
`run_id`, `phase`, `event`).

Quando usi `pipeline.logging_utils.phase_scope`, i log emettono automaticamente
gli stessi ID se `TIMMY_OTEL_ENDPOINT` è impostato.

Verifica:
- apri una trace view in Grafana (View logs / View trace),
- scegli la trace,
- clicca View logs per aprire Loki con filtri `trace_id`, `slug`, `run_id`.

---

## Query utili (Grafana / Loki)

- Errori di fase:
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

---

## Dashboard predefinite Timmy

- `TIMMY_GRAFANA_LOGS_UID`: UID della dashboard log (`observability/grafana-dashboards/logs-dashboard.json`).
  Il pannello *Log dashboard* (UI) apre la dashboard filtrata sullo `slug` attivo (`var-slug`).
- `TIMMY_GRAFANA_ERRORS_UID`: UID dashboard errori per fase (`observability/grafana-dashboards/errors-dashboard.json`).
  Il pulsante apre la dashboard con filtro `slug`/`phase` e query Loki `level="ERROR"`.

### Indicatori di stack (policy Beta 1.0)
- La UI mostra un badge `Grafana /` nella sezione osservabilità e lo aggiorna solo se Docker è attivo.
- Se Docker non è attivo, compare un messaggio informativo con il comando `{docker compose ... up -d}`.
  Start/Stop restano disabilitati fino a quel momento.
- Quando Docker è disponibile, i pulsanti `Start Stack` e `Stop Stack` invocano le funzioni
  in `tools/observability_stack.py` per lanciare `docker compose up -d` o `docker compose down`.
- Se l’avvio fallisce, la UI deve mostrare errore esplicito (non warning generico) e loggare
  un evento strutturato `observability.stack.start_failed` con l’errore sintetico.

I valori vengono letti in tempo reale e non ci sono side effect: basta aggiornare `.env`
(o i `TIMMY_*` dei container) e riavviare l’interfaccia.

---

## Helper CLI (tools/observability_stack)

Lo stesso helper `tools/observability_stack.py` è disponibile anche come script stand-alone:

```bash
python tools/observability_stack.py start
```

per avviare lo stack e:

```bash
python tools/observability_stack.py stop
```

per fermarlo. Lo script stampa l’output del `docker compose` e restituisce exit code `0`
solo in caso di successo.

Le opzioni `--env-file` / `--compose-file` permettono di sovrascrivere rispettivamente
`TIMMY_OBSERVABILITY_ENV_FILE` e `TIMMY_OBSERVABILITY_COMPOSE_FILE`
(default `.env` e `observability/docker-compose.yaml`).

---

## Span OTEL e attributi (telemetria)

La telemetria OTEL è composta da:

- **Trace root** (`timmy_kb.<journey>`, es. `timmy_kb.onboarding`, `timmy_kb.ingest`, `timmy_kb.reindex`)
  - Attributi: `slug`, `run_id`, `trace_kind`, `env`, `entry_point`, `journey`
- **Phase span** (`phase:<phase>`, aperto da `phase_scope`)
  - Attributi: `phase`, `slug`, `run_id`, `trace_kind`, `status`, `artifact_count`, `dataset_area`,
    `source_type`, `policy_id`, `rosetta_quality_score`, `risk_level`, `error_kind`, `error_code`
- **Decision span** (`decision:<decision_type>`)
  - Attributi: `decision_type`, `slug`, `run_id`, `trace_kind`, `phase`, `reason`, `policy_id`,
    `dataset_area`, `er_entity_type`, `er_relation_type`, `model_version`, `ambiguity_score`,
    `hilt_involved`, `user_role`, `override_reason`, `previous_value`, `new_value`, `status`

Grafana sfrutta `trace_id`, `span_id`, `slug`, `run_id`, `phase` e `decision_type` per incatenare trace e log.

---

## Human override spans (HiTL)

Ogni volta che l’amministratore UI salva/rigenera `tags_reviewed.yaml`,
il codice deve emettere un decision span con:
- `decision_type=human_override`
- `phase=ui.manage.tags_yaml`
- `hilt_involved=true`, `user_role`
- `previous_value` / `new_value`
- `status` (`success` / `failed`) e `reason`

Ogni cambio di stato deve essere tracciato come decisione (non come “side effect”),
per mantenere audit completo.

---

## Policy Beta 1.0 su “fallback” e resilienza semantica

In Beta 1.0 non sono ammessi downgrade silenziosi.
Le condizioni sotto sono ammesse solo se **esplicite e governate**.

### Loader `tags_reviewed` non disponibile
- Se `storage.tags_store.load_tags_reviewed` non è disponibile:
  - produrre evento strutturato `semantic.vocab_loader.unavailable`,
  - verdict di gate: `BLOCK` con `stop_code=HITL_REQUIRED`,
  - richiesta intervento (non stub automatico).
- La modalità “stub” è ammessa solo in contesti **test-only** esplicitamente dichiarati,
  mai in run normative.

### Embedding provider error
- Se `_compute_embeddings_for_markdown` riceve errore dal provider:
  - produrre evento `semantic.index.embedding_error`,
  - **FAIL** della run (stop governato) se l’embedding è richiesto per gli artefatti finali,
  - consentire retry come nuova run dopo correzione.
- Non è ammesso “continuare” restituendo `(None, 0)` come comportamento normale Beta 1.0.

---

## Decision span sampling

- `TIMMY_DECISION_SPAN_SAMPLING` (default `1.0`) controlla quanti micro-span vengono emessi.
- Il sampling è ammesso solo sulla telemetria OTEL:
  - non deve alterare log strutturati in Loki,
  - non deve alterare Decision Record o evidenze normative.

---

## Tracing doctor

- Il pannello Log UI può offrire un pulsante “Verifica tracing” che:
  - emette un trace diagnostico (`trace_kind=diagnostic`)
  - con `phase=observability.tracing.doctor`
  - e un log `observability.tracing.test_span_emitted`.
- Serve a verificare che il Collector riceva gli span dalla UI.

---

## Alerting critico

Per inviare alert in tempo reale (es. Slack, Sentry):
- configura Loki/Grafana con alert rules oppure
- imposta un receiver (es. Sentry) usando bridge OpenTelemetry.

Assicurati che eventuali token generati in GitHub Actions siano mascherati (`::add-mask::`)
prima di venire stampati nei log.

---

## Buone pratiche
- Evita di loggare variabili di ambiente o payload contenenti segreti.
- Usa `pipeline/logging_utils.get_structured_logger` per tutti i logger.
- Mantieni attivi i filtri di redazione e aggiorna `promtail-config.yaml`
  con pattern ulteriori qualora emergano nuovi tipi di credenziali.
