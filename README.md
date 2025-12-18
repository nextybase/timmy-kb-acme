# Timmy KB - README (v1.0 Beta)

Pipeline per generare una Knowledge Base Markdown pronta per l'uso AI a partire dai PDF del cliente, con arricchimento semantico e anteprima locale (HonKit).

[**Design premise:** il sistema è pensato per hardware dedicato e ambienti controllati, esegue processi automatizzati e usa regole/tests rigorosi per garantire riproducibilità e auditabilità: qualsiasi rottura deve fallire rumorosamente.]

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
- Namespace: i moduli sono importabili direttamente da `src` (es. `from ingest import ingest_folder`, `from pipeline.context import ClientContext`); il vecchio alias `timmykb.*` è stato rimosso.
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

### Prompt Chain (refactor sicuri)
Le modifiche significative, i refactor complessi o gli interventi multi-step effettuati tramite l'agente Codex seguono il modello **Prompt Chain**, descritto nello SSoT [`docs/PromptChain_spec.md`](docs/PromptChain_spec.md).

Una Prompt Chain garantisce che ogni step sia un micro-PR con QA, supervisionato dal Planner, e che la chiusura avvenga solo dopo aver portato a verde:
```
pre-commit run --all-files
pytest -q
```
Questo modello consente interventi profondi mantenendo massima sicurezza, coerenza e tracciabilita'.
Il ciclo completo è Planner → OCP → Codex → OCP → Planner, con Phase 0 dedicata all’analisi read-only, Phase 1..N ai micro-PR intermedi (con `pytest -q -k "not slow"` e Active Rules memo) e Prompt N+1 alla QA finale (`pre-commit run --all-files` + `pytest -q`) e al riepilogo italiano.
Per i dettagli operativi vedi `.codex/PROMPTS.md`, `docs/runbook_codex.md` e `.codex/WORKFLOWS.md`.

---

## Telemetria & sicurezza
- **Workspace slug-based:** Tutti i log operativi (output, ingest, UI, semantic) vivono sotto `output/timmy-kb-<slug>/logs/` con redazione automatica dei segreti; ogni componente scrive sotto il proprio slug/workspace e rispetta path-safety e scritture atomiche.
- **Global UI log guard:** L'handler condiviso `.timmykb/logs/ui.log` serve al viewer globale (Log dashboard) ma non ospita dati operativi o fallback di ingest; Promtail è configurato solo per leggere `output/timmy-kb-*/logs/*.log` e `.timmykb/logs/*.log` per le dashboard di grafana/tempo.
- Rotazione file (`RotatingFileHandler`) e tracing OTEL (configurazioni `TIMMY_LOG_*`, `TIMMY_OTEL_*`) sono gestiti come prima, senza introdurre meccanismi legacy.
- `pre-commit` include CSpell, gitleaks e controlli SPDX per mantenere documentazione e codice coerenti.
- Il push GitHub (`py src/onboarding_full.py`) usa `pipeline.github_utils.push_output_to_github`: prepara un clone temporaneo `.push_*`, copia solo i Markdown e gestisce retry/force push (`--force-with-lease`) secondo `TIMMY_NO_GITHUB`/`SKIP_GITHUB_PUSH`, `GIT_DEFAULT_BRANCH` e `GIT_FORCE_ALLOWED_BRANCHES` + `force_ack`.

### Observability stack (Loki + Grafana + Promtail)
- `observability/docker-compose.yaml` (Loki + Grafana + Promtail) legge solo `output/timmy-kb-*/logs/*.log` e il log UI globale (`.timmykb/logs/*.log`); non usa alcun fallback di storage.
- Le righe structured `slug=... run_id=... event=...` sono esportate come label Loki (`slug`, `run_id`, `event`) e alimentano liste di alert o dashboard.
- Avvia con:
  ```bash
  docker compose --env-file ./.env -f observability/docker-compose.yaml up -d
  ```
  Grafana (`http://localhost:3000`) usa `GRAFANA_ADMIN_PASSWORD` (fallback solo per dev); Loki è su `http://localhost:3100`.
- Personalizza i bind `./promtail-config.yaml`, `output` e `.timmykb/logs` a seconda del filesystem locale; spegni con `docker compose down`.

Per altre note operative (preview Docker, ingest CSV, gestione extras Drive) rimandiamo alle sezioni dedicate della [User Guide](docs/user_guide.md) e della [Developer Guide](docs/developer_guide.md).
