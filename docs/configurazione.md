# Configurazione (YAML, .env, OIDC)

Questa pagina raccoglie in un unico posto le regole di configurazione del progetto.
Si applica sia all’ambiente locale sia all’esecuzione CI (GitHub Actions).

## Single Source of Truth

| Ambito | Contenuto | Esempi ammessi | Esempi vietati |
|--------|-----------|----------------|----------------|
| `.env` (non versionato) | **Segreti** e valori runtime sensibili. Il codice li legge tramite nomi variabile (`*_env`). `.env.example` è l’unico file versionato. | `OPENAI_API_KEY=sk-live...`<br>`SERVICE_ACCOUNT_FILE=/path/sa.json`<br>`OIDC_AUDIENCE=https://token.actions` | `vision_model=gpt-4o-mini`<br>`candidate_limit=4000` |
| `config/config.yaml` (versionato) | **Configurazione applicativa**: modelli, limiti retriever, preferenze UI, mapping. Non contiene mai segreti. | `vision.model: gpt-4o-mini-2024-07-18`<br>`retriever.candidate_limit: 4000`<br>`ui.skip_preflight: true` | `openai_api_key: sk-...`<br>`drive_id: 1234567890`<br>`vault_token: ...` |

Regola d’oro: se un campo richiede un segreto, il valore in YAML **termina con `_env`**
e contiene solo il nome della variabile:

```yaml
vision:
  model: gpt-4o-mini-2024-07-18
  assistant_id_env: OBNEXT_ASSISTANT_ID
```

```yaml
# ✗ errato (mai salvare il segreto nel config)
vision:
  assistant_id: asst_dummy
```

## Config YAML

`config/config.yaml` è la SSoT applicativa. Oltre ai blocchi storici (retriever, vision,
ui, raw_cache) ospita la sezione `security.oidc` appena introdotta:

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
config “classica” e da `pipeline.oidc_utils.ensure_oidc` per il wiring OIDC.

## `.env` e placeholder

`.env.example` elenca le variabili attese: OpenAI, Drive, GitHub push, OIDC/Vault,
telemetria. Copia il file in `.env` e valorizza solo ciò che ti serve. Alcuni esempi:

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
`ci_required=true` ma mancano i prerequisiti: è eseguito automaticamente in CI quando
`OIDC_PROVIDER` è valorizzato.

## Telemetria & logging

`TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, `TIMMY_ENV` attivano la correlazione OTLP
già supportata da `pipeline.logging_utils` (trace_id/span_id). Imposta `LOG_REDACTION`
a `1/true` per forzare la redazione lato console/file.

## UI & guide

La guida Streamlit fa riferimento a questa pagina per i dettagli di configurazione.
Per una panoramica dei flussi UI consulta [docs/guida_ui.md](guida_ui.md).

## Tooling

- Il hook `no-secrets-in-yaml` blocca commit sospetti (`api_key`, `token`, `secret`, `password`).
- La pagina Streamlit **Secrets Healthcheck** (Tools → Secrets Healthcheck) mostra lo stato
  delle variabili richieste senza rivelarle.
- `Settings.env_catalog()` elenca le variabili attese, utile per documentazione e
  validazioni automatiche.

Per il razionale di separazione segreti/config consulta l’ADR
[0002-separation-secrets-config](adr/0002-separation-secrets-config.md).
