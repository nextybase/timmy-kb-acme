# Timmy KB - README (v1.0 Beta)

Timmy-KB è un ambiente per la creazione e il governo di Timmy: attraverso una pipeline di fondazione inghiotte dati, produce output deterministici (derivatives) e abilita l'emergere controllato dell'agency, restando HiTL e mantenendo governance by design.

[**Design premise:** il sistema è pensato per hardware dedicato e ambienti controllati, esegue processi automatizzati e usa regole/test rigorosi per garantire riproducibilità e auditabilità: qualsiasi rottura deve fallire rumorosamente.]

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![CI](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml/badge.svg)](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml)
[![Security Status](https://img.shields.io/badge/security-hardened-brightgreen)](docs/policies/security.md)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE.md)

Timmy-KB è l'implementazione operativa che incarna i principi del framework NeXT: mantiene l'envelope epistemico, resta Human-in-the-Loop e imposta governance by design; NeXT è la cornice teorica che descrive l'AI come strumento di supporto, non come autorità autonoma.

Cornice filosofica e di responsabilità: [MANIFEST.md](MANIFEST.md).

---

## Prerequisiti rapidi
- Python >= 3.11, `pip` e `pip-tools`
- (Opz.) Docker per la preview HonKit
- Credenziali Google Drive (Service Account JSON) se usi la sorgente Drive
- Le credenziali (es. service_account.json, OPENAI_API_KEY) restano fuori dal repo e vanno fornite via `.env`/file locali non tracciati

Variabili d'ambiente principali: `OPENAI_API_KEY`, `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `LOG_REDACTION`.
Per il logging avanzato usa `TIMMY_LOG_MAX_BYTES`, `TIMMY_LOG_BACKUP_COUNT`, `TIMMY_LOG_PROPAGATE`, `TIMMY_OTEL_ENDPOINT`, `TIMMY_SERVICE_NAME`, `TIMMY_ENV`.

---

## Quickstart essenziale

### Interfaccia Streamlit
```bash
python -m streamlit run src/timmy_kb/ui/onboarding_ui.py
```
La UI guida l'onboarding end-to-end. Per flussi completi e screenshot consulta la [User Guide](docs/user/user_guide.md).

### CLI automatizzata
```bash
python -m timmy_kb.cli.pre_onboarding --slug acme --name "Cliente ACME" --non-interactive
python -m timmy_kb.cli.tag_onboarding --slug acme --non-interactive --proceed
python -m timmy_kb.cli.semantic_onboarding --slug acme --non-interactive
```
```
Ogni step puo' essere eseguito singolarmente; l'orchestrazione dettagliata e' descritta nella [User Guide](docs/user/user_guide.md). Il flusso termina con la preview locale via Docker/HonKit (pipeline `honkit_preview`).

## ⚠️ Beta constraint: Strict vs Dummy mode

In Beta, il flusso di onboarding è **strict by default**:
la generazione degli stub semantici è **disabilitata** e lo stato massimo
raggiungibile è `TAGS_CSV_READY`.

L'esecuzione end-to-end è consentita **solo** tramite flag esplicito
`--dummy` ed è sempre **tracciata nel _Decision Ledger_**.

👉 Dettagli operativi e implicazioni di audit:
**[Strict vs Dummy - Guida Operativa](docs/strict_vs_dummy_beta.md)**.

## ✅ Beta: State Model (Decision Ledger = SSoT)

In Beta, il `workspace_state` è derivato esclusivamente dal Decision Ledger (SSoT).
Lo stato canonico è ancorato alla `latest_run` (regressione ammessa).
Nessun motore di stato separato: niente ricomposizioni tra run.
Il modello di stato è la specifica per stati, transizioni e regole di derivazione.
Usalo per interpretare il ledger in modo deterministico.
👉 **[State Model (Beta 1.0)](docs/developer/state_model.md)**.


### Igiene workspace
- I derivatives runtime restano fuori dal controllo versione e fuori dalla repo root: `output/`, `logs/`, `.timmy_kb/`, `.streamlit/`, cache pytest/ruff/mypy e `node_modules/` sono ignorati.
- Se compaiono nel working tree, rimuovili prima di eseguire un commit o spostali fuori dal repository. Vedi [Developer Guide](docs/developer/developer_guide.md) (ALERT / Workspace Discipline).

---

## Dipendenze & QA
- Installa gli ambienti tramite i pin generati con `pip-compile` (`requirements*.txt`). Maggiori dettagli in [docs/developer/configurazione.md](docs/developer/configurazione.md).
- Il vocabolario richiede PyYAML. Non sono supportati parser di fallback o retrocompat: usa `semantic/tags.db` come SSoT runtime e `semantic/tags_reviewed.yaml` solo come artefatto di editing.
- Namespace: i moduli sono importabili direttamente da `src` (es. `from timmy_kb.cli.ingest import ingest_folder`, `from pipeline.context import ClientContext`); gli alias di import legacy sono stati rimossi, usa il namespace attuale.
- Hook consigliati:
  ```bash
  pre-commit install --hook-type pre-commit
  make qa-safe     # lint + typing
  pytest -q        # suite rapida (dataset dummy)
  ```
- Per l'elenco completo dei test e dei tag consulta [docs/developer/test_suite.md](docs/developer/test_suite.md).

---

## Documentazione & riferimenti
- [User Guide](docs/user/user_guide.md) - flussi UI/CLI, Vision, workspace.
- [Developer Guide](docs/developer/developer_guide.md) - SSoT, pipeline, logging, get_vision_model().
- [Coding Rules](docs/developer/coding_rule.md) e [Architecture Overview](system/architecture.md).
- [Configuration split](docs/developer/configurazione.md) e [Runbook Codex](system/ops/runbook_codex.md).
- [CONTRIBUTING](CONTRIBUTING.md) - policy PR e micro-PR.
- [LICENSE](LICENSE.md) - GPL-3.0.
- [Code of Conduct](CODE_OF_CONDUCT.md) e [Security](SECURITY.md).

La pipeline produce output necessari (derivatives) e orchestra l'emergere di agenti HiTL e micro-agenti sotto supervisione umana, mantenendo l'envelope epistemico come limite operativo.

## From Foundation Pipeline to Agency
- La pipeline di ingestione è l'atto di nascita di Timmy: nasce quando i PDF del cliente vengono trasformati in markdown semanticamente arricchiti e il knowledge graph associato viene validato.
- Solo a quel punto il passaggio concettuale ProtoTimmy → Timmy diventa operativo: ProtoTimmy governa la fondazione, Timmy assume agency globale e dialoga con Domain Gatekeepers e micro-agent.
- La pipeline non decide né orchestra: è lo strumento che genera output (markdown + knowledge graph) richiesti dallo SSoT e abilita il control plane, ma la direzione resta affidata a Timmy e ai gatekeeper.
- Tutti i riferimenti tecnici a `pipeline.*` descrivono gli strumenti operativi della fondazione; dopo la validazione la Prompt Chain documentata in `instructions/` prende il comando.

La sezione seguente descrive il passaggio dalla fondazione alla fase di agency governata, mantenendo sempre la supervisione umana.

---

### Prompt Chain (refactor sicuri)
Le modifiche significative, i refactor complessi o gli interventi multi-step effettuati tramite l'agente Codex seguono il modello **Prompt Chain**, descritto nello SSoT [`system/specs/promptchain_spec.md`](system/specs/promptchain_spec.md).

Una Prompt Chain garantisce che ogni step sia un micro-PR con QA, supervisionato dal Planner, e che la chiusura avvenga solo dopo aver portato a verde:
```
pre-commit run --all-files
pytest -q
```
Questo modello consente interventi profondi mantenendo massima sicurezza, coerenza e tracciabilita'.
Il ciclo completo è Planner → OCP → Codex → OCP → Planner, con Phase 0 dedicata all'analisi read-only, Phase 1..N ai micro-PR intermedi (con `pytest -q -k "not slow"` e Active Rules memo) e Prompt N+1 alla QA finale (`pre-commit run --all-files` + `pytest -q`) e al riepilogo italiano.
Per i dettagli operativi vedi `.codex/PROMPTS.md`, `system/ops/runbook_codex.md` e `.codex/WORKFLOWS.md`.

---

## Telemetria & sicurezza
- **Workspace slug-based:** Tutti i log operativi vivono nel workspace cliente; in setup locali tipicamente sotto `output/timmy-kb-<slug>/logs/` con redazione automatica dei segreti. Ogni componente scrive sotto il proprio slug/workspace e rispetta path-safety e scritture atomiche.
- **Global UI log guard:** L'handler condiviso dei log UI globali serve al viewer (Log dashboard) ma non ospita dati operativi o fallback di ingest; quando il workspace ? locale, Promtail ? configurato per leggere `output/timmy-kb-*/logs/*.log` e i log UI globali per le dashboard di grafana/tempo.
- Rotazione file (`RotatingFileHandler`) e tracing OTEL (configurazioni `TIMMY_LOG_*`, `TIMMY_OTEL_*`) sono gestiti come prima, senza introdurre meccanismi legacy.
- `pre-commit` include CSpell, gitleaks e controlli SPDX per mantenere documentazione e codice coerenti.

### Observability stack (Loki + Grafana + Promtail)
- `observability/docker-compose.yaml` (Loki + Grafana + Promtail) legge i log del workspace locale (`output/timmy-kb-*/logs/*.log`) e i log UI globali; non usa alcun fallback di storage.
- Le righe structured `slug=... run_id=... event=...` sono esportate come label Loki (`slug`, `run_id`, `event`) e alimentano liste di alert o dashboard.
- Avvia con:
  ```bash
  docker compose --env-file ./.env -f observability/docker-compose.yaml up -d
  ```
  Grafana (`http://localhost:3000`) usa `GRAFANA_ADMIN_PASSWORD` (fallback solo per dev); Loki è su `http://localhost:3100`.
- Personalizza i bind `./promtail-config.yaml` e `output` a seconda del filesystem locale; spegni con `docker compose down`.

Per altre note operative (preview Docker, ingest CSV, gestione extras Drive) rimandiamo alle sezioni dedicate della [User Guide](docs/user/user_guide.md) e della [Developer Guide](docs/developer/developer_guide.md).
