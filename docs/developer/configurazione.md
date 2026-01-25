# Configurazione (YAML, .env, OIDC)

Questa pagina raccoglie in un unico posto le regole di configurazione del progetto.
Si applica sia all'ambiente locale sia all'esecuzione CI (GitHub Actions).

## Single Source of Truth

| Ambito | `config/config.yaml` (SSoT non segreto) | `.env` (segreti/processo) |
|--------|-----------------------------------------|---------------------------|
| **Meta** | `meta.client_name`, `meta.N_VER`, `meta.DATA_VER` |  |
| **OpenAI** | `ai.openai.timeout: 120`<br>`ai.openai.max_retries: 2`<br>`ai.openai.http2_enabled: false` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_PROJECT` |
| **Vision** | `ai.vision.model: gpt-4o-mini-2024-07-18`<br>`ai.vision.engine: assistants`<br>`ai.vision.snapshot_retention_days: 30`<br>`ai.vision.assistant_id_env: OBNEXT_ASSISTANT_ID` (solo il nome ENV)<br>`ai.vision.vision_statement_pdf: config/VisionStatement.pdf` | `OBNEXT_ASSISTANT_ID` |
| **UI** | `ui.skip_preflight`, `ui.allow_local_only`, `ui.admin_local_mode` |  |
| **Retriever** | `pipeline.retriever.auto_by_budget`, `pipeline.retriever.throttle.latency_budget_ms`, `candidate_limit`, `parallelism`, `sleep_ms_between_calls` |  |
| **Cache RAW** | `pipeline.raw_cache.ttl_seconds`, `pipeline.raw_cache.max_entries` |  |
| **Ops / Logging** | `ops.log_level: INFO` | `TIMMY_LOG_MAX_BYTES`, `TIMMY_LOG_BACKUP_COUNT`, `TIMMY_LOG_PROPAGATE` |
| **Security / OIDC** | riferimenti `*_env` (audience_env, role_env, ...) | `SERVICE_ACCOUNT_FILE`, `ACTIONS_ID_TOKEN_REQUEST_*`, ecc. |
| **Runtime/Infra** |  | `PYTHONUTF8`, `PYTHONIOENCODING`, `GF_SECURITY_ADMIN_PASSWORD`, `TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, `TIMMY_ENV`, `LOG_REDACTION`, `LOG_PATH`, `CI`, ecc. |

### Accesso runtime (SSoT)

- **Config globale**: usa sempre `pipeline.settings.Settings.load(...)` oppure `ClientContext.settings`; la UI passa da `ui.config_store.get_vision_model()` (nessuna lettura YAML diretta).
- **Config cliente**: API unificata `pipeline.config_utils.load_client_settings(context)` → `context.settings` → dict via `.as_dict()`.
- **Segreti**: recuperati solo via `Settings.resolve_env_ref` / `Settings.get_secret`; evitare `os.environ[...]` per credenziali nei call-site applicativi.

> **Nota:** una *deny-list* interna impedisce di spostare in YAML variabili che devono
> rimanere nello `.env`. Se configuri per errore chiavi come `OPENAI_API_KEY` o
> `SERVICE_ACCOUNT_FILE` nel file YAML, verranno ignorate (con warning
> `settings.yaml.env_denied`) e lapp continuera a leggere tali valori solo
> da l'ambiente.

> **Nota 1.0:** per ogni funzionalità operativa viene richiesta solo `OPENAI_API_KEY`; non esistono alternative legacy.

Regola doro: se un campo richiede un segreto, il valore in YAML **termina con `_env`**
e contiene solo il nome della variabile:

```yaml
ai:
  vision:
    model: gpt-4o-mini-2024-07-18
    assistant_id_env: OBNEXT_ASSISTANT_ID
```

```yaml
#  errato (mai salvare il segreto nel config)
ai:
  vision:
    assistant_id: asst_dummy
```

## Config YAML

`config/config.yaml` è la SSoT applicativa strutturata per macro-sezioni:

- `meta`: nome cliente e versioning (`N_VER`, `DATA_VER`).
- `ui`: `skip_preflight`, `allow_local_only`, `admin_local_mode`.
- `ai.openai`: timeout (s), max_retries, `http2_enabled`.
- `ai.vision`: modello, engine (enum `assistants|responses|...`), `snapshot_retention_days`, `use_kb`, `strict_output`, riferimenti *_env ai segreti.
- `pipeline.retriever.throttle`: `candidate_limit`, `latency_budget_ms`, `parallelism`, `sleep_ms_between_calls`; flag `auto_by_budget`.
- `pipeline.raw_cache`: `ttl_seconds`, `max_entries`.
- `ops`: `log_level` per i logger applicativi.
- `integrations`: sezione mostrata in UI Configurazione (valori operativi per integrazioni esterne).
- `rosetta`: flag `rosetta.enabled` e `rosetta.provider` letti dal client Rosetta.
- `slug_regex`: regex opzionale per validare gli slug (fallback: `^[a-z0-9-]+$`). Segnale: nessun segnale/log esplicito documentato.

Sezioni assistant (letto da `ai.assistant_registry`):
- `ai.prototimmy`, `ai.planner_assistant`, `ai.ocp_executor`, `ai.audit_assistant`, `ai.kgraph`
  con `model`, `assistant_id_env`, `use_kb` (per audit: `model` + `assistant_id_env`).

La sezione `security.oidc` resta invariata e segue qui sotto:

```yaml
security:
  oidc:
    enabled: false
    provider: "vault"
    audience_env: OIDC_AUDIENCE
    issuer_url_env: OIDC_ISSUER_URL
    role_arn_env: OIDC_ROLE_ARN
    gcp_provider_env: OIDC_GCP_PROVIDER
    azure_fedcred_env: OIDC_AZURE_FEDCRED
    vault:
      addr_env: VAULT_ADDR
      role_env: VAULT_ROLE
      jwt_path_env: OIDC_JWT_PATH
    ci_required: false
```

Lato codice le impostazioni sono consumate da `pipeline.settings.Settings` per la
config classica e da `pipeline.oidc_utils.ensure_oidc` per il wiring OIDC.

## `.env` e placeholder

`.env.example` elenca le variabili attese: OpenAI, Drive, OIDC/Vault,
telemetria. Copia il file in `.env` e valorizza solo cio che ti serve. Alcuni esempi:

```dotenv
OIDC_PROVIDER=vault            # o: aws | gcp | azure | generic
OIDC_AUDIENCE=https://token.actions
OIDC_ISSUER_URL=https://token.actions.githubusercontent.com
VAULT_ADDR=https://vault.example.com
VAULT_ROLE=timmy-kb
```

In CI puoi usare le Repository Variables (`vars.`) per esporre il provider e leggere
gli altri valori da Secrets o da un Secret Manager esterno.

## OIDC (locale & CI)

Il modulo `pipeline.oidc_utils.ensure_oidc_context(...)` consuma `security.oidc`
dal YAML e risolve i valori *_env dall'ambiente:

1. Legge `security.oidc` (provider, nomi delle ENV).
2. Recupera un ID token (preferibilmente via GitHub Actions, fallback a file `.jwt` locale). Segnale: nessun segnale/log esplicito documentato.
3. Se `provider=vault`, scambia il JWT con un client token (`VAULT_TOKEN`) tramite login standard.
4. Restituisce un dizionario di variabili da esportare/loggare (mai il token vero).

Campi YAML vs env:
- YAML: `security.oidc.enabled`, `security.oidc.provider`, `security.oidc.*_env`.
- Env risolti: i valori puntati da `audience_env`, `role_env`, `token_request_url_env`,
  `token_request_token_env` (oltre a `ACTIONS_ID_TOKEN_REQUEST_*` in GitHub Actions).

Comportamento: se `enabled=false` la funzione ritorna `enabled: False` senza errore; se
`enabled=true` la risoluzione OIDC è fail-fast e solleva `ConfigError` quando
mancano variabili richieste o il token non è ottenibile (evidenza: `src/pipeline/oidc_utils.py`).

Lo script `tools/ci/oidc_probe.py` richiama `ensure_oidc` e fallisce quando
`ci_required=true` ma mancano i prerequisiti: e eseguito automaticamente in CI quando
`OIDC_PROVIDER` e valorizzato.

## Telemetria & logging

`TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, `TIMMY_ENV` attivano la correlazione OTLP
gia supportata da `pipeline.logging_utils` (trace_id/span_id). Imposta `LOG_REDACTION`
a `1/true` per forzare la redazione lato console/file.

## UI & guide

La guida Streamlit fa riferimento a questa pagina per i dettagli di configurazione.
Per una panoramica dei flussi UI consulta [docs/user/guida_ui.md](user/guida_ui.md).

## Tooling

- Il hook `no-secrets-in-yaml` blocca commit sospetti (`api_key`, `token`, `secret`, `password`).
- La pagina Streamlit **Secrets Healthcheck** (Tools  Secrets Healthcheck) mostra lo stato
  delle variabili richieste senza rivelarle.
- `Settings.env_catalog()` elenca le variabili attese, utile per documentazione e
  validazioni automatiche.

Per il razionale di separazione segreti/config consulta lADR
[0002-separation-secrets-config](adr/0002-separation-secrets-config.md).

## Appendice: note operative

## File candidati legacy in config/ (evidenze repo-wide)

Classificazione (cautelativa): **UNUSED_UNKNOWN** per tutti i file elencati.
L'evidenza e' una ricerca repo-wide senza occorrenze; non e' prova definitiva
perche' potrebbero esistere usi esterni, dinamici o non versionati.

- `config/config.yaml.bak`
  - Evidenza: nessuna occorrenza trovata con pattern
    `config/config.yaml.bak|config\\config.yaml.bak|config.yaml.bak`.
  - Limite: possibili usi esterni/dinamici/non versionati.
- `config/pdf_dummy.yaml`
  - Evidenza: nessuna occorrenza trovata con pattern
    `config/pdf_dummy.yaml|config\\pdf_dummy.yaml|pdf_dummy.yaml`.
  - Limite: possibili usi esterni/dinamici/non versionati.
- `config/tags_template.yaml`
  - Evidenza: nessuna occorrenza trovata con pattern
    `config/tags_template.yaml|config\\tags_template.yaml|tags_template.yaml`.
  - Limite: possibili usi esterni/dinamici/non versionati.
