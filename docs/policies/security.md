# Security & Compliance Guide (Beta 1.0)

Questa pagina definisce le **policy operative di sicurezza e compliance**
per il repository `timmy-kb-acme`.

Il documento è **normativo** per la Beta 1.0:
- non descrive "best practice opzionali",
- non introduce fallback impliciti,
- non autorizza degradazioni silenziose del runtime.

Ogni violazione delle policy qui definite deve produrre
un errore esplicito o uno stop governato.

---

## Gestione dei segreti

### Principi generali (Beta 1.0)
- I segreti **non devono mai** essere versionati nel repository.
- Ogni meccanismo di risoluzione dei segreti deve essere:
  - esplicito,
  - verificabile,
  - auditabile.
- L'assenza o l'invalidità di un segreto **non è recuperabile automaticamente**.

### Modalità ammesse

#### Secret Manager (consigliato)
- Archivia i valori sensibili (API key, token Slack, ecc.) in:
  - GitHub Actions Secrets, oppure
  - un Secret Manager dedicato.
- I secret sono risolti **a runtime** e non persistono su disco.

#### OIDC (preferito)
- Le credenziali statiche sono sostituite da ruoli federati.
- Nel workflow `ci.yaml` è disponibile un blocco OIDC basato su:
  `aws-actions/configure-aws-credentials@<PIN_SHA>`.
- Le variabili `TIMMY_SERVICE_NAME` e `TIMMY_ENV` sono obbligatorie.
- Quando OIDC è attivo:
  - non è consentito l'uso di access key statiche,
  - l'autenticazione è **fail-fast**.

#### Modalità senza OIDC (esplicita, non fallback)
- Se `security.oidc.enabled=false`, l'uso di secret statici è
  una **scelta dichiarata di configurazione**, non un fallback.
- Questa modalità:
  - deve essere documentata nel contesto di deployment,
  - resta soggetta a rotazione e scanning obbligatori.
- Non esiste alcuna modalità "best-effort" o automatica.

---

## OIDC Configuration (Local & CI)

- Configura `security.oidc` in `config/config.yaml`
  (provider, audience, variabili `_env`).
- Valorizza le ENV in `.env` o Repository Variables:
  `OIDC_*`, `VAULT_*`.
- Quando `security.oidc.enabled=true`:
  - la risoluzione OIDC è **fail-fast**,
  - variabili mancanti o token non ottenibile ⇒ errore esplicito.
- Lo step **OIDC probe** in `ci.yaml` esegue `tools/ci/oidc_probe.py`
  solo se `GITHUB_OIDC_AUDIENCE` è valorizzata.
- Per rendere OIDC obbligatorio in CI:
  ```yaml
  security:
    oidc:
      ci_required: true
  ```
- Consultare `docs/configurazione.md` per il dettaglio completo.

---

## Secret Scanning

- Workflow dedicato: `.github/workflows/secret-scan.yml`.
- Esegue `gitleaks detect --report-format sarif`.
- Il report è caricato su GitHub Code Scanning.

### Vincoli Beta 1.0
- `Secret Scan` è **required status check** su `main`.
- Una violazione blocca il merge.
- Non sono ammesse deroghe silenziose.

### Esecuzione locale
```bash
gitleaks detect --source . --no-git
```

---

## Dependency Scanning

- Workflow `.github/workflows/dependency-scan.yml`:
  - esegue `pip-audit` su `requirements.txt` e `requirements-dev.txt`,
  - su ogni PR verso `main`/`dev` e su base settimanale.
- Il job fallisce in presenza di CVE non ignorate.

### Gestione eccezioni
- I falsi positivi vanno dichiarati in `.pip-audit-ignore`
  con motivazione esplicita.
- Le eccezioni sono **auditabili** e versionate.

### Esecuzione locale
```bash
pip install pip-audit
pip-audit -r requirements.txt -r requirements-dev.txt
```

---

## Pre-commit Hooks

- `.pre-commit-config.yaml` include:
  - `gitleaks`,
  - `detect-secrets` (baseline `.secrets.baseline`).
- Installazione locale:
```bash
pip install pre-commit
pre-commit install --hook-type pre-commit
```
- Rigenerazione baseline:
```bash
detect-secrets scan --baseline .secrets.baseline
```

---

## Docker & Container Hardening

- Workflow `.github/workflows/docker-lint.yml`:
  - esegue `hadolint` su ogni Dockerfile (PR + weekly).
- Anche in assenza di Dockerfile, il controllo resta attivo.

### Linee guida normative
- Immagini base minimali (`python:3.11-slim`, distroless se possibile).
- Esecuzione non-root (`USER app`).
- Rimozione tool di build a fine stage.
- I secret **non** devono essere:
  - hardcoded,
  - passati via `ENV` o `ARG`.

### Esecuzione locale
```bash
hadolint path/to/Dockerfile
```

---

## Protezione dei Branch

Configurazione raccomandata su `main`:

1. **Require a pull request before merging**
   - Minimum 1 approval
   - Dismiss stale reviews
   - Require conversation resolution
2. **Require status checks**
   - `CI`
   - `Secret Scan`
3. **Include administrators**
4. **Restrict who can write**
   - solo bot o release manager
5. *(Opzionale)* Require signed commits

Script opzionale:
`tools/apply_branch_protection.sh` (uso manuale, non in CI).

---

## Logging & Alerting

- Tutti i moduli devono usare
  `pipeline.logging_utils.get_structured_logger`.
- Header sensibili (`Authorization`, `x-access-token`) sono mascherati.
- È vietato serializzare:
  - payload completi,
  - variabili d'ambiente non filtrate.
- In caso di dubbio, usare `extra={...}` filtrato.

### Tracing
- Se `TIMMY_OTEL_ENDPOINT` è impostato:
  - vengono generati `trace_id` e `span_id`.
- Vedi `docs/observability.md`.

---

## Query Operative (Loki / Grafana)

- Errori di fase:
```logql
{job="timmy-kb", event="phase_failed"}
```

- Ricerca per workspace e semantic module:
```logql
{slug="acme"} |~ "semantic.index"
```

---

## Clausola di Coerenza
Ogni modifica a:
- workflow CI/CD,
- policy di sicurezza,
- meccanismi di autenticazione,

**deve** essere riflessa:
- in questo documento,
- nelle branch protection rules,
- nei file di configurazione.

La divergenza tra comportamento e questa guida
è da considerarsi **non conforme** alla Beta 1.0.

## Enforcement & References

- **Enforcement:**
  - CI workflows: [secret-scan](../../.github/workflows/secret-scan.yml),
    [dependency-scan](../../.github/workflows/dependency-scan.yml),
    [docker-lint](../../.github/workflows/docker-lint.yml).
  - Pre-commit hooks: [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml).
  - Branch protection e required checks su `main` (processo repo).
- **References:**
  - [Coding Rules](../developer/coding_rule.md)
  - [Architecture Overview](../../system/architecture.md)
  - [Configurazione](../configurazione.md)
  - [MANIFEST.md](../../MANIFEST.md)
