from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_ui_beta0_compliance() -> None:
    """Richiama lo script di compliance e fallisce se vengono rilevate violazioni."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "check_ui_beta0_compliance.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        message = "\n".join(part for part in (stdout, stderr) if part) or "check_ui_beta0_compliance.py failed"
        raise AssertionError(message)
