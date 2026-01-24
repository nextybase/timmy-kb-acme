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

# 4) Preview locale (HonKit via Docker): gestita via adapter/UI (vedi runbook)
# non esiste un entrypoint `python -m pipeline.honkit_preview`
```
Note: in locale il workspace vive di default in `output/timmy-kb-<slug>/` (derivatives); in ambienti dedicati usa un workspace fuori dalla repo root. Vedi [Coding Rules](coding_rule.md#workspace-discipline-repo-vs-runtime).

## Flusso 2: UI Streamlit + workspace cliente
```bash
python -m streamlit run onboarding_ui.py
```
- Seleziona/crea lo slug dal pannello iniziale (registry UI).
- Gating: la tab **Semantica** si attiva solo con `normalized/` presente; i percorsi sono validati via path-safety.
- Il modello Vision ? letto da `ui.config_store.get_vision_model()` ? SSoT `config/config.yaml`.
- Diagnostica runtime (opt-in): `set DEBUG_RUNTIME=1` e `python tools/smoke/kb_healthcheck.py --slug dummy --force`.
- Diagnostica offline: `python tools/smoke/kb_healthcheck.py --slug dummy --offline` (valida artefatti Vision senza chiamate rete).
- Eseguire sempre gli smoke con `.\.venv\Scripts\python.exe ...` (Windows) o `./.venv/bin/python ...` (Unix).
- `python -m pip index versions openai`
- `python -m pip install -U "openai>=X"`
- `python tests/scripts/openai_responses_signature.py`
- Dummy smoke offline: `python tools/gen_dummy_kb.py --slug dummy --no-drive` (nessun Drive, niente deep-testing).
- Dummy deep-testing (richiede Drive): `python tools/gen_dummy_kb.py --slug dummy --deep-testing`.
  `--no-drive --deep-testing` è un conflitto e deve fallire.

## Flusso 3: Aggiunta nuovo cliente (registry UI)
- Apri la UI, vai su **Gestisci cliente** ? **Nuovo cliente**.
- Inserisci slug/nome; il registry ? gestito da `ui.clients_store` (SSoT runtime).
- La configurazione cliente viene creata nel workspace cliente (default locale: `output/timmy-kb-<slug>/config/config.yaml`) e letta via `pipeline.config_utils.get_client_config(context)`.

## QA rapidi consigliati
- `make qa-safe` (isort/black/ruff/mypy).
- `make type` (mypy) o `make ci-safe` (qa + pytest) prima di aprire una PR.
- cSpell su docs: `pre-commit run cspell --files docs/developer/developer_quickstart.md`.

## Link utili
- Developer Guide: contesto e onboarding (non normativo).
- Coding Rules: regole operative e stile.
- Architecture Overview: mappa dei componenti e responsabilita.
- Runbook Codex: flussi operativi per agenti (path-safety, scritture atomiche).
- Configurazione: esempi e regole per `config/config.yaml` e `.env`.
