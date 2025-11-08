# Timmy KB - README (v1.0 Beta)

Pipeline per generare una Knowledge Base Markdown pronta per l'uso AI a partire dai PDF del cliente, con arricchimento semantico, anteprima locale (HonKit) e push opzionale su GitHub.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![CI](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml/badge.svg)](https://github.com/nextybase/timmy-kb-acme/actions/workflows/ci.yaml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

---

## Prerequisiti rapidi
- Python >= 3.11, `pip` e `pip-tools`
- (Opz.) Docker per la preview HonKit
- Credenziali Google Drive (Service Account JSON) se usi la sorgente Drive
- Token GitHub se abiliti il push finale

Variabili d'ambiente principali: `OPENAI_API_KEY` (o `OPENAI_API_KEY_FOLDER`), `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `GITHUB_TOKEN`, `LOG_REDACTION`.

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
- Installa gli ambienti tramite i pin generati con `pip-compile` (`requirements*.txt`). Maggiori dettagli in [docs/configuration.md](docs/configuration.md).
- L'import del vocabolario (`tags_reviewed.yaml`) funziona anche senza PyYAML grazie a un parser fallback minimale, ma per YAML complessi raccomandiamo di installare PyYAML: in fallback viene emesso il log `storage.tags_store.import_yaml.fallback`.
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
- [Configuration split](docs/configuration.md) e [Runbook Codex](docs/runbook_codex.md).
- [CONTRIBUTING](CONTRIBUTING.md) - policy PR e micro-PR.
- [LICENSE](LICENSE) - GPL-3.0.
- [Code of Conduct](CODE_OF_CONDUCT.md) e [Security](SECURITY.md).

---

## Telemetria & sicurezza
- Logging strutturato centralizzato sotto `output/timmy-kb-<slug>/logs/` con redazione automatica dei segreti.
- Path-safety e scritture atomiche per ogni operazione su workspace/Drive.
- CSpell, gitleaks e controlli SPDX sono inclusi nella configurazione `pre-commit`.
- Il push GitHub (`py src/onboarding_full.py`) usa `pipeline.github_utils.push_output_to_github`: prepara un clone temporaneo `.push_*`, copia solo i Markdown e gestisce retry/force push (`--force-with-lease`) secondo `TIMMY_NO_GITHUB`/`SKIP_GITHUB_PUSH`, `GIT_DEFAULT_BRANCH` e `GIT_FORCE_ALLOWED_BRANCHES` + `force_ack`.

Per altre note operative (preview Docker, ingest CSV, gestione extras Drive) rimandiamo alle sezioni dedicate della [User Guide](docs/user_guide.md) e della [Developer Guide](docs/developer_guide.md).
