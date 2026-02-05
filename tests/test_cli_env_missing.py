# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pipeline.exceptions import ConfigError, exit_code_for
from tests._helpers.workspace_paths import local_workspace_dir

PY = sys.executable


def test_tag_onboarding_cli_missing_env_returns_configerror_code(tmp_path: Path) -> None:
    slug = "dummy"
    client_dir = local_workspace_dir(tmp_path, slug)
    client_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    # Garantisce workspace isolato (evita scritture fuori sandbox test)
    env["WORKSPACE_ROOT_DIR"] = str(client_dir)
    env.pop("REPO_ROOT_DIR", None)
    # Rimuovi le variabili richieste dalla sorgente Drive
    env.pop("SERVICE_ACCOUNT_FILE", None)
    env.pop("DRIVE_ID", None)

    repo_root = Path(__file__).resolve().parents[1]
    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    proc = subprocess.run(
        [
            PY,
            "-m",
            "timmy_kb.cli.tag_onboarding",
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
