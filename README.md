# Timmy KB - README (v1.0 Beta)

Pipeline per generare una Knowledge Base Markdown pronta per l'uso AI a partire dai PDF del cliente, con arricchimento semantico, anteprima locale (HonKit) e push opzionale su GitHub.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![CI](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml/badge.svg)](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml)
[![Security Status](https://img.shields.io/badge/security-hardened-brightgreen)](docs/security.md)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

---

## Prerequisiti rapidi
- Python >= 3.11, `pip` e `pip-tools`
- (Opz.) Docker per la preview HonKit
- Credenziali Google Drive (Service Account JSON) se usi la sorgente Drive
- Token GitHub se abiliti il push finale

Variabili d'ambiente principali: `OPENAI_API_KEY`, `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `GITHUB_TOKEN`, `LOG_REDACTION`.
Per il logging avanzato usa `TIMMY_LOG_MAX_BYTES`, `TIMMY_LOG_BACKUP_COUNT`, `TIMMY_LOG_PROPAGATE`, `TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, `TIMMY_ENV`.

---

## Quickstart essenziale

### Interfaccia Streamlit
```bash
streamlit run onboarding_ui.py
```
La UI guida l'onboarding end-to-end. Per flussi completi e screenshot consulta la [User Guide](docs/user_guide.md).

### CLI automatizzata
```bash
py src/pre_onboarding.py --slug acme --name "Cliente ACME" --non-interactive
py src/tag_onboarding.py --slug acme --non-interactive --proceed
py src/semantic_onboarding.py --slug acme --non-interactive
py src/onboarding_full.py --slug acme --non-interactive
```
Ogni step puo' essere eseguito singolarmente; l'orchestrazione dettagliata e' descritta nella [User Guide](docs/user_guide.md).

---

## Dipendenze & QA
- Installa gli ambienti tramite i pin generati con `pip-compile` (`requirements*.txt`). Maggiori dettagli in [docs/configurazione.md](docs/configurazione.md).
- L'import del vocabolario (`tags_reviewed.yaml`) funziona anche senza PyYAML grazie a un parser fallback minimale, ma per YAML complessi raccomandiamo di installare PyYAML: in fallback viene emesso il log `storage.tags_store.import_yaml.fallback`.
- Namespace: i moduli sono importabili direttamente da `src` (es. `from ingest import ingest_folder`, `from pipeline.context import ClientContext`); il vecchio alias `timmykb.*` � stato rimosso.
- Hook consigliati:
  ```bash
  pre-commit install --hook-type pre-commit --hook-type pre-push
  make qa-safe     # lint + typing
  pytest -q        # suite rapida (dataset dummy)
  ```
- Per l'elenco completo dei test e dei tag consulta [docs/test_suite.md](docs/test_suite.md).

---

## Documentazione & riferimenti
- [User Guide](docs/user_guide.md) - flussi UI/CLI, Vision, workspace.
- [Developer Guide](docs/developer_guide.md) - SSoT, pipeline, logging, get_vision_model().
- [Coding Rules](docs/coding_rule.md) e [Architecture Overview](docs/architecture.md).
- [Configuration split](docs/configurazione.md) e [Runbook Codex](docs/runbook_codex.md).
- [CONTRIBUTING](CONTRIBUTING.md) - policy PR e micro-PR.
- [LICENSE](LICENSE) - GPL-3.0.
- [Code of Conduct](CODE_OF_CONDUCT.md) e [Security](SECURITY.md).

---

## Telemetria & sicurezza
- Logging strutturato centralizzato sotto `output/timmy-kb-<slug>/logs/` con redazione automatica dei segreti (token/password/key/service_account). L'entrypoint UI crea l'handler condiviso `.timmykb/logs/ui.log` e propaga agli altri logger `ui.*`.
- I log globali della UI (Streamlit) sono salvati in `.timmykb/logs/` e visibili dalla pagina Log dashboard; Promtail estrae `slug/run_id/event` (e, se OTEL attivo, `trace_id/span_id` nei campi log) per la correlazione Grafana/Tempo.
- La rotazione file (`RotatingFileHandler`) si regola tramite ENV `TIMMY_LOG_MAX_BYTES` / `TIMMY_LOG_BACKUP_COUNT` (default: 1 MiB, 3 backup).
- L'esportazione tracing (OTel) si attiva impostando `TIMMY_OTEL_ENDPOINT` (OTLP/HTTP), `TIMMY_SERVICE_NAME` e `TIMMY_ENV`; gli entrypoint CLI sono gia avvolti in `start_root_trace`.
- Path-safety e scritture atomiche per ogni operazione su workspace/Drive.
- CSpell, gitleaks e controlli SPDX sono inclusi nella configurazione `pre-commit`.
- Il push GitHub (`py src/onboarding_full.py`) usa `pipeline.github_utils.push_output_to_github`: prepara un clone temporaneo `.push_*`, copia solo i Markdown e gestisce retry/force push (`--force-with-lease`) secondo `TIMMY_NO_GITHUB`/`SKIP_GITHUB_PUSH`, `GIT_DEFAULT_BRANCH` e `GIT_FORCE_ALLOWED_BRANCHES` + `force_ack`.

### Observability stack (Loki + Grafana + Promtail)
- Compose file in `observability/docker-compose.yaml` con Loki, Promtail e Grafana; la configurazione Promtail (file `observability/promtail-config.yaml`) legge `output/timmy-kb-*/logs/*.log` e `.timmykb/logs/*.log`.
- Le righe structured `slug=... run_id=... event=...` vengono esposte come label Loki (`slug`, `run_id`, `event`), pronte per dashboard e alert.
- Avvio rapido (usa il `.env` in **root**):
  ```bash
  docker compose --env-file ./.env -f observability/docker-compose.yaml up -d
  ```
  Grafana e su `http://localhost:3000` (utente `admin`; password letta da `GRAFANA_ADMIN_PASSWORD` nel `.env` di root, con fallback `admin`); Loki risponde su `http://localhost:3100`.
- Personalizza i bind `./promtail-config.yaml`, `output` e `.timmykb/logs` in base al tuo filesystem locale. Spegni con `docker compose down`.

Per altre note operative (preview Docker, ingest CSV, gestione extras Drive) rimandiamo alle sezioni dedicate della [User Guide](docs/user_guide.md) e della [Developer Guide](docs/developer_guide.md).
