# Configurazione (YAML, .env, OIDC)

Questa pagina raccoglie in un unico posto le regole di configurazione del progetto.
Si applica sia all'ambiente locale sia all'esecuzione CI (GitHub Actions).

## Single Source of Truth

| Ambito | `config/config.yaml` (SSoT non segreto) | `.env` (segreti/processo) |
|--------|-----------------------------------------|---------------------------|
| **Meta** | `meta.client_name`, `meta.semantic_mapping_yaml`, `meta.vision_statement_pdf`, `meta.N_VER`, `meta.DATA_VER` |  |
| **OpenAI** | `ai.openai.timeout: 120`<br>`ai.openai.max_retries: 2`<br>`ai.openai.http2_enabled: false` | `OPENAI_API_KEY`, `OPENAI_API_KEY_CODEX`, `OPENAI_BASE_URL`, `OPENAI_PROJECT` |
| **Vision** | `ai.vision.model: gpt-4o-mini-2024-07-18`<br>`ai.vision.engine: assistants`<br>`ai.vision.snapshot_retention_days: 30`<br>`ai.vision.assistant_id_env: OBNEXT_ASSISTANT_ID` (solo il nome ENV) | `OBNEXT_ASSISTANT_ID`, `ASSISTANT_ID` |
| **UI** | `ui.skip_preflight`, `ui.allow_local_only`, `ui.admin_local_mode` |  |
| **Retriever** | `pipeline.retriever.auto_by_budget`, `pipeline.retriever.throttle.latency_budget_ms`, `candidate_limit`, `parallelism`, `sleep_ms_between_calls` |  |
| **Cache RAW** | `pipeline.raw_cache.ttl_seconds`, `pipeline.raw_cache.max_entries` |  |
| **Ops / Logging** | `ops.log_level: INFO` | `TIMMY_LOG_MAX_BYTES`, `TIMMY_LOG_BACKUP_COUNT`, `TIMMY_LOG_PROPAGATE` |
| **Finance** | `finance.import_enabled: false` |  |
| **Security / OIDC** | riferimenti `*_env` (audience_env, role_env, ...) | `GITHUB_TOKEN`, `SERVICE_ACCOUNT_FILE`, `ACTIONS_ID_TOKEN_REQUEST_*`, ecc. |
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

- `meta`: nome cliente, riferimenti SSoT (`semantic_mapping_yaml`, `vision_statement_pdf`), versioning (`N_VER`, `DATA_VER`).
- `ui`: `skip_preflight`, `allow_local_only`, `admin_local_mode`.
- `ai.openai`: timeout (s), max_retries, `http2_enabled`.
- `ai.vision`: modello, engine (enum `assistants|responses|...`), `snapshot_retention_days`, `use_kb`, riferimenti *_env ai segreti.
- `pipeline.retriever.throttle`: `candidate_limit`, `latency_budget_ms`, `parallelism`, `sleep_ms_between_calls`; flag `auto_by_budget`.
- `pipeline.raw_cache`: `ttl_seconds`, `max_entries`.
- `ops`: `log_level` per i logger applicativi.
- `finance`: `import_enabled` per attivare il flusso Finance.

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

`.env.example` elenca le variabili attese: OpenAI, Drive, GitHub push, OIDC/Vault,
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

Il modulo `pipeline.oidc_utils` espone `ensure_oidc(settings)`:

1. Legge `security.oidc` (provider, nomi delle ENV).
2. Recupera un ID token (preferibilmente via GitHub Actions, fallback a file `.jwt` locale).
3. Se `provider=vault`, scambia il JWT con un client token (`VAULT_TOKEN`) tramite login standard.
4. Restituisce un dizionario di variabili da esportare/loggare (mai il token vero).

Lo script `scripts/ci/oidc_probe.py` richiama `ensure_oidc` e fallisce quando
`ci_required=true` ma mancano i prerequisiti: e eseguito automaticamente in CI quando
`OIDC_PROVIDER` e valorizzato.

## Telemetria & logging

`TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, `TIMMY_ENV` attivano la correlazione OTLP
gia supportata da `pipeline.logging_utils` (trace_id/span_id). Imposta `LOG_REDACTION`
a `1/true` per forzare la redazione lato console/file.

## UI & guide

La guida Streamlit fa riferimento a questa pagina per i dettagli di configurazione.
Per una panoramica dei flussi UI consulta [docs/guida_ui.md](guida_ui.md).

## Tooling

- Il hook `no-secrets-in-yaml` blocca commit sospetti (`api_key`, `token`, `secret`, `password`).
- La pagina Streamlit **Secrets Healthcheck** (Tools  Secrets Healthcheck) mostra lo stato
  delle variabili richieste senza rivelarle.
- `Settings.env_catalog()` elenca le variabili attese, utile per documentazione e
  validazioni automatiche.

Per il razionale di separazione segreti/config consulta lADR
[0002-separation-secrets-config](adr/0002-separation-secrets-config.md).
