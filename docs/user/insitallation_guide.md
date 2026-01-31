# Installation Guide (v1.0 Beta)

Guida passo-passo per installare Timmy-KB in locale. Questa guida descrive
solo l'installazione; per l'uso operativo vedi la User Guide.

## 1) Requisiti software (verifica preliminare)

Obbligatori:
- Python 3.11.x (esatto: 3.11)
- pip (incluso con Python)
- pip-tools (solo se devi rigenerare requirements)
- Git

Opzionali:
- Docker (per preview HonKit)
- ReportLab (per README.pdf in raw/)

Verifica versioni:
```bash
python --version
pip --version
git --version
```

Se Python non e' 3.11.x, installa la versione corretta prima di proseguire.

## 2) Clona il repository

```bash
git clone <repo-url>
cd timmy-kb-acme
```

## 3) Crea e attiva il virtualenv

Crea il venv nella root del repo:
```bash
python -m venv .venv
```

Attiva il venv:

Windows (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
```

Windows (cmd):
```cmd
.\.venv\Scripts\activate.bat
```

macOS/Linux (bash/zsh):
```bash
source .venv/bin/activate
```

Verifica che il venv sia attivo:
```bash
python --version
```

## 4) Aggiorna pip (consigliato)

```bash
python -m pip install --upgrade pip
```

## 5) Installa le dipendenze

Installazione base (runtime):
```bash
pip install -r requirements.txt
```

Dipendenze di sviluppo (lint, typecheck, test):
```bash
pip install -r requirements-dev.txt
```

Dipendenze opzionali (Drive integration):
```bash
pip install -r requirements-optional.txt
```

Nota: se devi rigenerare i requirements, usa `pip-compile` sui file `.in`
secondo la policy in `docs/developer/coding_rule.md`.

## 6) Configura le variabili ambiente (.env)

Le credenziali non vanno in repo. Crea un file `.env` locale con:
- `OPENAI_API_KEY` (obbligatoria per funzioni AI)
- `SERVICE_ACCOUNT_FILE` e `DRIVE_ID` (solo se usi Drive)

Esempio minimo:
```bash
OPENAI_API_KEY="..."
```

## 7) Pre-commit (consigliato)

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## 8) Smoke check (opzionale)

```bash
python tools/test_runner.py fast
```

Se il comando fallisce, non procedere: risolvi prima i problemi di setup.

Nota (Dummy strict): se esegui `tools/gen_dummy_kb.py` con `TIMMY_BETA_STRICT=1`,
imposta `WORKSPACE_ROOT_DIR` al workspace canonico (es. `output/timmy-kb-<slug>`) prima del run.
In strict è **vietato** puntare a `.../output` senza il suffisso `timmy-kb-<slug>`: il runtime richiede
che `WORKSPACE_ROOT_DIR` risolva direttamente alla directory `output/timmy-kb-<slug>` e fallirà con
`workspace.root.invalid` se viene passato il parent `output` o un nome diverso dallo slug atteso.

## 9) Prossimi passi (comandi separati)

Test architettura (guardrail struttura):
```bash
python tools/test_runner.py arch
```

Avvio UI (Streamlit):
```bash
python -m streamlit run src/timmy_kb/ui/onboarding_ui.py
```

Altri riferimenti:
- User Guide: `docs/user/user_guide.md`
- Quickstart: `docs/user/quickstart.md`
