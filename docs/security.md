# Security & Compliance Guide

Questa pagina descrive le policy operative per proteggere il repository `timmy-kb-acme`.

## Gestione dei segreti

- **Secret Manager (consigliato)**: archivia i valori sensibili (API key, token Slack, ecc.)
  in GitHub Actions Secrets oppure in un Secret Manager dedicato.
- **OIDC (preferito)**: sostituisci le credenziali statiche con ruoli federati.
  Nel workflow `ci.yaml` trovi un blocco commentato che usa
  `aws-actions/configure-aws-credentials@<PIN_SHA>` con le variabili
  `TIMMY_SERVICE_NAME` e `TIMMY_ENV`. Abilitando il ruolo OIDC non Ã¨ piÃ¹ necessario salvare
  access key nel repository.
- **Fallback**: i secrets esistenti restano supportati; assicurati perÃ² di ruotarli periodicamente.

## OIDC config (local & CI)

- Imposta la sezione `security.oidc` in `config/config.yaml` (provider, variabili `_env`).
- Valorizza le ENV in `.env`/Repository Variables (`OIDC_*`, `VAULT_*`).
- Lo step "OIDC probe (optional)" in `ci.yaml` esegue `scripts/ci/oidc_probe.py` quando la variabile `GITHUB_OIDC_AUDIENCE` è valorizzata.
- Consulta [docs/configurazione.md](configurazione.md) per il dettaglio completo.

## Secret scanning

- Workflow dedicato: `.github/workflows/secret-scan.yml`.
  Esegue `gitleaks detect --report-format sarif` e carica il report su GitHub Code Scanning.
- **Required status check**: abilita `Secret Scan` insieme a `CI` nelle branch protection rules.
- Per una scansione locale:
  ```bash
  gitleaks detect --source . --no-git
  ```

## Dependency scanning

- Workflow `.github/workflows/dependency-scan.yml` esegue `pip-audit` su `requirements.txt` e `requirements-dev.txt`
  ad ogni push/PR su `main`/`dev` e settimanalmente (`cron`).
- Il risultato SARIF viene caricato su GitHub Code Scanning; il job fallisce se ci sono CVE non ignorate.
- Per gestire falsi positivi, usa il file `.pip-audit-ignore` ed aggiorna questa sezione indicando la motivazione della deroga.
- Esecuzione locale:
  ```bash
  pip install pip-audit
  pip-audit -r requirements.txt -r requirements-dev.txt
  ```

## Pre-commit hooks

- Il file `.pre-commit-config.yaml` include i controlli per gitleaks e `detect-secrets`
  (baseline `.secrets.baseline`).
- Installa gli hook una tantum:
  ```bash
  pip install pre-commit
  pre-commit install --hook-type pre-commit --hook-type pre-push
  ```
- Per rigenerare la baseline vuota:
  ```bash
  detect-secrets scan --baseline .secrets.baseline
  ```

## Docker & container hardening

- Workflow `.github/workflows/docker-lint.yml` esegue `hadolint` su ogni Dockerfile del repo (push/PR + weekly).
  Attualmente il repository non contiene Dockerfile; il job riporta il salto ma resta attivo per future integrazioni.
- Linee guida per i Dockerfile:
  - usa immagini base minimali (`python:3.11-slim`, distroless dove possibile);
  - aggiungi `USER app` o equivalente per evitare l'esecuzione come `root`;
  - elimina tool di build al termine (`apt-get purge`, `rm -rf /var/lib/apt/lists/*`);
  - leggi i secret esclusivamente da variabili a runtime (non `ENV`/`ARG` hardcoded).
- Per i `docker-compose`/deployment assicurati che i secret provengano da GitHub Secrets o Secret Manager esterni.
- Esecuzione locale di `hadolint`:
  ```bash
  hadolint path/to/Dockerfile
  ```

## Protezione dei branch

Configura la regola su `main` (GitHub â†’ Settings â†’ Branches):

1. **Require a pull request before merging**
   - Minimum 1 approval
   - Dismiss stale reviews
   - Require conversation resolution
2. **Require status checks to pass before merging**
   - `CI`
   - `Secret Scan`
3. **Include administrators** (Enforce for administrators)
4. **Restrict who can push** (solo bot o release manager)
5. *(Facoltativo)* Require signed commits

Script opzionale (`scripts/apply_branch_protection.sh`) mostra i comandi `gh api`
per applicare automaticamente la policy (non eseguire in CI).

## Logging & Alerting

- Tutti i moduli devono usare `pipeline.logging_utils.get_structured_logger`.
- Il logging redige automaticamente header sensibili (`Authorization`, `x-access-token`) e
  maschera pattern comuni.
- Evita di serializzare payload completi o variabili di ambiente. In caso di dubbio,
  passa gli extra nel campo `extra={...}` dopo averli filtrati.
- Per alert in tempo reale abilita un ricevitore (Slack/Sentry) o usa i campi `trace_id`/`span_id`
  generati quando `TIMMY_OTEL_ENDPOINT` Ã¨ impostato (vedi `docs/observability.md`).

## Query rapide (Loki / Grafana)

- Log di errori di fase:
  ```logql
  {job="timmy-kb", event="phase_failed"}
  ```
- Ricerca per cliente e modulo semantic:
  ```logql
  {slug="acme"} |~ "semantic.index"
  ```

Mantieni questi documenti sincronizzati con gli aggiornamenti dei workflow: qualsiasi cambiamento
alle pipeline CI/CD deve essere riflesso sia nelle branch protection rules sia nelle istruzioni
di secret management.
