# Timmy-KB â€“ Release Notes v2.0.0 (2025-09-20)

Questa release si concentra su robustezza delle integrazioni Drive, chiarezza degli errori e installazione nativa via pyproject.

NovitÃ  principali
- Guardie esplicite per Google Drive:
  - Orchestratori: `pre_onboarding` e `tag_onboarding` validano la disponibilitÃ  delle funzioni Drive prima dell'uso.
  - UI: `ui/services/drive_runner.py` valida gli helper Drive e carica `.env` in modo idempotente.
- Installazione nativa: extra `drive` in `pyproject.toml` (`pip install .[drive]`), con dipendenze base per `pip install .`.
- Workflows CI opzionali non-gating (import-smoke, bench) confermati.

Impatto per gli utenti
- Se i pacchetti Drive non sono installati, CLI e UI mostrano un messaggio chiaro con l'istruzione `pip install .[drive]` invece di errori generici.
- La UI carica automaticamente `.env` (se presente) e verifica `SERVICE_ACCOUNT_FILE` e `DRIVE_ID`.

Aggiornamento
1) Aggiorna dipendenze (consigliato):
   ```bash
   pip install -r requirements.txt
   # oppure
   pip install -e .
   pip install .[drive]
   ```
2) Verifica `.env` in root repo:
   ```env
   SERVICE_ACCOUNT_FILE=path\al\service_account.json
   DRIVE_ID=xxxxxxxxxxxxxxxx
   ```

Note tecniche
- Versione pacchetto aggiornata a `2.0.0` in `pyproject.toml`.
- `src/tag_onboarding.py`: `_require_drive_utils()` invocato nel ramo `source=="drive"`.
- `src/ui/services/drive_runner.py`: guardie su `emit_readmes_for_raw` e `download_raw_from_drive_with_progress`.
