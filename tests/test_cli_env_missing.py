from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pipeline.exceptions import ConfigError, exit_code_for

PY = sys.executable


def test_tag_onboarding_cli_missing_env_returns_configerror_code(tmp_path: Path) -> None:
    slug = "env-miss"
    client_dir = tmp_path / f"timmy-kb-{slug}"
    client_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    # Garantisce workspace isolato (evita scritture fuori sandbox test)
    env["REPO_ROOT_DIR"] = str(client_dir)
    # Rimuovi le variabili richieste dalla sorgente Drive
    env.pop("SERVICE_ACCOUNT_FILE", None)
    env.pop("DRIVE_ID", None)

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            PY,
            str(repo_root / "src" / "tag_onboarding.py"),
            "--slug",
            slug,
            "--non-interactive",
            # default source = drive (require_env=True)
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == exit_code_for(ConfigError("x"))
    # Assicurati che non ci siano tracebacks grezzi (messaggio conciso)
    assert "Traceback" not in (proc.stdout + proc.stderr)
