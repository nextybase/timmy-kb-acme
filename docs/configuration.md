# Configurazione – .env vs config.yaml

Questa pagina chiarisce la separazione **configurazioni vs segreti** introdotta nel progetto.
L’obiettivo è ridurre il rischio di commit accidentali di credenziali, mantenendo le
impostazioni di business/UX versionate in modo sicuro.

## Single Source of Truth

| Ambito | Contenuto | Esempi ammessi | Esempi vietati |
|--------|-----------|----------------|----------------|
| `.env` (non versionato) | **Segreti** e valori runtime sensibili, referenziati dal codice tramite nomi di variabile. Deve restare fuori dal repository (solo `.env.example` è versionato). | `OPENAI_API_KEY=sk‑live‑…`<br>`OBNEXT_ASSISTANT_ID=asst_123`<br>`SERVICE_ACCOUNT_FILE=C:\path\sa.json` | `vision_model=<modello legacy>`<br>`candidate_limit=4000` |
| `config/config.yaml` (versionato) | **Configurazione applicativa mutabile**: modelli, soglie, mapping UI, parametri retriever, preferenze logging. Non contiene mai valori segreti. | `vision.model: <modello predefinito>`<br>`retriever.candidate_limit: 3000`<br>`ui.skip_preflight: true` | `openai_api_key: sk-…`<br>`drive_id: 1234567890`<br>`assistant_id: asst_123` |

> ℹ️ Se un campo ha bisogno di un segreto, il valore nel YAML **deve terminare con**
> `_env` e contenere solo il nome della variabile, non il valore:

```yaml
# ✅ corretto
vision:
  model: "<modello predefinito>"
  assistant_id_env: OBNEXT_ASSISTANT_ID
```

```yaml
# ❌ errato: il valore del segreto non deve stare nel config
vision:
  assistant_id: asst_dummy
```

## Esempi di utilizzo

- **Accesso al segreto**:

  ```python
  from pipeline.settings import Settings

  settings = Settings.load(repo_root)
  assistant_id = settings.resolve_env_ref("vision.assistant_id_env", required=True)
  ```

- **Override applicativo**:

  ```yaml
  retriever:
    candidate_limit: 2500
    latency_budget_ms: 120
  ```

## Tooling

- Hook locale/CI `no-secrets-in-yaml` impedisce commit con chiavi come `api_key`, `token`, `secret`, `password` in `config/*.ya?ml`.
- Pagina Streamlit **Secrets Healthcheck** (`Tools → Secrets Healthcheck`) mostra lo stato delle variabili attese senza rivelarne il valore.
- Il catalogo variabili di riferimento è esposto da `Settings.env_catalog()`.

Per i dettagli di design consulta l’ADR dedicato: [0002-separation-secrets-config](adr/0002-separation-secrets-config.md).
