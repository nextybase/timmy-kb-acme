# Timmy KB - README (v1.9.5 Alpha, pre-1.0 Beta)

Current release: 1.9.5 Alpha · Upcoming release: 1.0 Beta (pre-release coordination).

Timmy-KB è un ambiente per la creazione e il governo di Timmy, strutturato su due domini epistemici distinti:
**Epistemic Envelope** e **Agency Engine**.

- L'**Epistemic Envelope** realizza la fondazione: ingestione e trasformazione dei dati in artefatti osservabili e deterministici (derivatives), con tracciabilità e auditabilità.
- L'**Agency Engine** realizza l'agency governata: Prompt Chain, gate, work orders e micro-agenti in modalità HiTL, con probabilismo confinato entro l'envelope.

[**Design premise:** il sistema è pensato per hardware dedicato e ambienti controllati, esegue processi automatizzati e usa regole/test rigorosi per garantire riproducibilità e auditabilità: qualsiasi rottura deve fallire rumorosamente.]

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![CI](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml/badge.svg)](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml)
[![Security Status](https://img.shields.io/badge/security-hardened-brightgreen)](docs/policies/security.md)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE.md)

## CI enforcement

Il workflow CI ha un job `Smoke / Strict Gates` che esegue `python tools/smoke/check_strict_workspace_gates.py` prima di lanciare la suite completa: fa fallire subito bootstrap e override quando `TIMMY_BETA_STRICT=1` e i flag `TIMMY_ALLOW_*` sono assenti, così eventuali regressioni "auto-consenso" vengono scoperte in pochi secondi.

Timmy-KB è l'implementazione operativa che incarna i principi del framework NeXT: mantiene l'envelope epistemico, resta Human-in-the-Loop e imposta governance by design; NeXT è la cornice teorica che descrive l'AI come strumento di supporto, non come autorità autonoma.

Cornice filosofica e di responsabilità: [MANIFEST.md](MANIFEST.md).

Installazione step-by-step: [Guida installazione](docs/user/insitallation_guide.md).

---

## Quickstart essenziale

Guida rapida: [User Quickstart](docs/user/quickstart.md).

### Interfaccia Streamlit
```bash
python -m streamlit run src/timmy_kb/ui/onboarding_ui.py
```
La UI guida l'onboarding end-to-end. Per flussi completi consulta la [User Guide](docs/user/user_guide.md).

### CLI automatizzata
```bash
python -m timmy_kb.cli.pre_onboarding --slug acme --name "Cliente ACME" --non-interactive
python -m timmy_kb.cli.tag_onboarding --slug acme --non-interactive --proceed
python -m timmy_kb.cli.semantic_onboarding --slug acme --non-interactive
```
Ogni step puo' essere eseguito singolarmente; l'orchestrazione dettagliata e' descritta nella [User Guide](docs/user/user_guide.md). Il flusso termina con la preview locale via Docker/HonKit (pipeline `honkit_preview`).

## ⚠️ Beta constraint: Strict vs Dummy mode

In Beta, il flusso di onboarding è **strict-by-default**: l'assenza o il valore vuoto di
`TIMMY_BETA_STRICT` equivale a strict, e la generazione degli stub semantici resta **disabilitata**.
Solo un valore esplicitamente falsy (`0`, `false`, `no`, `off`) su `TIMMY_BETA_STRICT`,
combinato con il flag `--dummy` e `TIMMY_ALLOW_DUMMY=1`, consente una run non-strict
tracciata e contenuta nel ledger.

Nota importante: il gate `tag_onboarding` è **intra-state** su `SEMANTIC_INGEST`
(nessuna transizione di stato nel Decision Ledger).

L'esecuzione end-to-end (con generazione stub) è consentita **solo** tramite flag esplicito
`--dummy` *e* capability gate `TIMMY_ALLOW_DUMMY=1`, ed è sempre **tracciata nel _Decision Ledger_**.

Attenzione: anche se esplicita e tracciata, la modalita' `--dummy` resta una **eccezione pericolosa**
rispetto all'obiettivo deterministico e a bassa entropia. Genera materiale non derivato da evidenza reale.
In strict mode gli stub sono vietati dal contratto runtime e qualsiasi tentativo di forzarli deve
portare a BLOCK. Non deve esistere (ne' essere introdotta) alcuna via laterale "comoda" nel runtime.

Nota operativa: quando la dummy gira con `TIMMY_BETA_STRICT=0/false/no/off`, `WORKSPACE_ROOT_DIR` deve
punta al workspace canonico (es. `output/timmy-kb-<slug>`). Non indicare il parent `output` senza lo slug,
è obbligatorio passare la directory finale `timmy-kb-<slug>` o il processo fallirà con `workspace.root.invalid`.

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
- Se compaiono nel working tree, rimuovili prima di eseguire un commit o spostali fuori dal repository. Vedi [Coding Rules](docs/developer/coding_rule.md#workspace-discipline-repo-vs-runtime).

---

## Dipendenze & QA
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
- [Guida installazione](docs/user/insitallation_guide.md) - setup passo-passo.
- [User Quickstart](docs/user/quickstart.md) - avvio rapido UI/CLI.
- [User Guide](docs/user/user_guide.md) - flussi UI/CLI, Vision, workspace.
- [Developer Guide](docs/developer/developer_guide.md) - contesto e onboarding (non normativo).
- [Coding Rules](docs/developer/coding_rule.md) e [Architecture Overview](system/architecture.md).
- [Configuration split](docs/developer/configurazione.md) e [Runbook Codex](system/ops/runbook_codex.md).
- [CONTRIBUTING](CONTRIBUTING.md) - policy PR e micro-PR.
- [LICENSE](LICENSE.md) - GPL-3.0.
- [Code of Conduct](CODE_OF_CONDUCT.md) e [Security](SECURITY.md).

L'**Epistemic Envelope** produce i derivatives necessari e costruisce il perimetro epistemico operativo.
L'**Agency Engine** orchestra l'emergere controllato dell'agency (Prompt Chain, gate e micro-agenti) sotto supervisione umana (HiTL), entro i vincoli dell'envelope.

## From Epistemic Envelope to Agency Engine
- L'**Epistemic Envelope** (foundation pipeline) è l'atto di nascita operativo di Timmy: quando i PDF del cliente vengono trasformati in markdown semanticamente arricchiti e il Knowledge Graph associato viene validato.
- Solo a quel punto il passaggio concettuale ProtoTimmy → Timmy diventa operativo: ProtoTimmy governa la fondazione (Epistemic Envelope), Timmy assume agency globale nell'Agency Engine e dialoga con Domain Gatekeepers e micro-agent.
- L'Epistemic Envelope **non decide né orchestra**: genera output (markdown + knowledge graph + lineage/ledger) richiesti dallo SSoT e abilita l'Agency Engine, ma la direzione resta affidata a Timmy e ai gatekeeper.
- Tutti i riferimenti tecnici a `pipeline.*` descrivono strumenti dell'Epistemic Envelope; dopo la validazione la Prompt Chain documentata in `instructions/` prende il comando nell'Agency Engine.

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
- **Global UI log guard:** L'handler condiviso dei log UI globali serve al viewer (Log dashboard) ma non ospita dati operativi o degradazioni di ingest; quando il workspace ? locale, Promtail ? configurato per leggere `output/timmy-kb-*/logs/*.log` e i log UI globali per le dashboard di grafana/tempo.
- Rotazione file (`RotatingFileHandler`) e tracing OTEL (configurazioni `TIMMY_LOG_*`, `TIMMY_OTEL_*`) sono gestiti come prima, senza introdurre meccanismi legacy.
- `pre-commit` include CSpell, gitleaks e controlli SPDX per mantenere documentazione e codice coerenti.

### Observability stack (Loki + Grafana + Promtail)
- `observability/docker-compose.yaml` (Loki + Grafana + Promtail) legge i log del workspace locale (`output/timmy-kb-*/logs/*.log`) e i log UI globali; non usa alcuna degradazione di storage.
- Le righe structured `slug=... run_id=... event=...` sono esportate come label Loki (`slug`, `run_id`, `event`) e alimentano liste di alert o dashboard.
- Avvia con:
  ```bash
  docker compose --env-file ./.env -f observability/docker-compose.yaml up -d
  ```
  Grafana (`http://localhost:3000`) usa `GRAFANA_ADMIN_PASSWORD` (default solo per dev); Loki è su `http://localhost:3100`.
- Personalizza i bind `./promtail-config.yaml` e `output` a seconda del filesystem locale; spegni con `docker compose down`.

Per altre note operative (preview Docker, ingest CSV, gestione extras Drive) rimandiamo alle sezioni dedicate della [User Guide](docs/user/user_guide.md) e della [Developer Guide](docs/developer/developer_guide.md).
