Security — SCA (Software Composition Analysis)

- Dependabot: attivo sull’ecosistema pip (pyproject.toml e requirements.txt) con cadenza settimanale. Apre PR automatiche per advisory note.
- Controllo in CI: job “Security Audit (pip-audit)” esegue
  - install: `pip install pip-audit`
  - scan: `pip-audit --strict --severity-level critical`
    - Pull Request: soft gate (continue-on-error: true)
    - main: fallisce in presenza di vulnerabilità critiche

Esecuzione locale

- pip install pip-audit
- pip-audit --strict --severity-level critical -P pyproject.toml -r requirements.txt

Note

- GitHub Actions (Dependabot): aggiornamenti delle action in `.github/workflows` con PR settimanali.
- Il job analizza sia il manifest `pyproject.toml` (PEP 621) sia `requirements.txt` quando presenti.
- Per ulteriori dettagli consultare la tab “Actions” → workflow “Security Audit (pip-audit)”.
