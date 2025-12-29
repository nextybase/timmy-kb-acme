# Developer Quickstart (v1.0 Beta)

Percorso minimo per sviluppatori e agenti Codex: comandi lineari, SSoT rispettate, niente sorprese.

## Prerequisiti rapidi
- Python ≥ 3.11, dipendenze installate: `pip install -r requirements.txt -r requirements-dev.txt`.
- Config SSoT globale: `config/config.yaml` (solo tramite `pipeline.settings.Settings` / `ClientContext.settings`).
- Segreti: `.env` letto da `Settings.resolve_env_ref` (mai `os.environ` diretto).
- Path-safety/I/O: sempre `ensure_within*` + `safe_write_*` (già usati dagli orchestratori).

## Flusso 1: CLI end-to-end (happy path)
```bash
# 1) Pre-onboarding: crea workspace e copia template semantic
python -m timmy_kb.cli.pre_onboarding --slug <slug> --name "<Cliente>" --non-interactive

# 2) Tag onboarding (estrazione tag + DB sqlite SSoT)
python -m timmy_kb.cli.tag_onboarding --slug <slug> --non-interactive --proceed

# 3) Semantic onboarding (convert ? enrich ? README/SUMMARY)
python -m timmy_kb.cli.semantic_onboarding --slug <slug> --non-interactive

# 4) Push opzionale (GitBook/preview): usa solo il workspace appena creato
py src/onboarding_full.py --slug <slug> --non-interactive
```
Note: il workspace vive in `output/timmy-kb-<slug>/`; non manipolare YAML/JSON a mano, passa sempre dalle API pipeline/semantic.

## Flusso 2: UI Streamlit + workspace cliente
```bash
streamlit run onboarding_ui.py
```
- Seleziona/crea lo slug dal pannello iniziale (registry UI).
- Gating: la tab **Semantica** si attiva solo con `raw/` presente; i percorsi sono validati via path-safety.
- Il modello Vision ? letto da `ui.config_store.get_vision_model()` ? SSoT `config/config.yaml`.

## Flusso 3: Aggiunta nuovo cliente (registry UI)
- Apri la UI, vai su **Gestisci cliente** ? **Nuovo cliente**.
- Inserisci slug/nome; il registry ? gestito da `ui.clients_store` (SSoT runtime).
- La configurazione cliente viene creata in `output/timmy-kb-<slug>/config/config.yaml` e letta via `pipeline.config_utils.get_client_config(context)`.

## QA rapidi consigliati
- `make qa-safe` (isort/black/ruff/mypy).
- `make type` (mypy) o `make ci-safe` (qa + pytest) prima di aprire una PR.
- cSpell su docs: `pre-commit run cspell --files docs/developer/developer_quickstart.md`.

## Link utili
- Developer Guide: principi architetturali, SSoT e policy operative.
- Runbook Codex: flussi operativi per agenti (path-safety, scritture atomiche).
- Configurazione: esempi e regole per `config/config.yaml` e `.env`.
