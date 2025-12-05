# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: S101,S603
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_dummy_cli_smoke(tmp_path: Path) -> None:
    """Esegue gen_dummy_kb in sandbox temporanea e verifica il payload health."""
    slug = "dummy"
    base_dir = tmp_path / "workspace"
    clients_db_relative = Path("clients_db/clients.yaml")

    script = Path(__file__).resolve().parents[2] / "tools" / "gen_dummy_kb.py"
    cmd = [
        sys.executable,
        str(script),
        "--slug",
        slug,
        "--base-dir",
        str(base_dir),
        "--clients-db",
        clients_db_relative.as_posix(),
        "--no-drive",
    ]

    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        assert (
            result.returncode == 0
        ), f"CLI fallita: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

        stdout = result.stdout
        json_start = stdout.find("{")
        assert json_start != -1, f"JSON non trovato in stdout:\n{stdout}"
        payload = json.loads(stdout[json_start:])
        health = payload.get("health") or {}

        assert "health" in payload, "Campo health mancante"
        assert health.get("mapping_valid") is True
        assert int(health.get("raw_pdf_count", 0)) >= 1
        if health.get("vision_status") == "ok":
            assert health.get("fallback_used") is False
        base = Path(payload["paths"]["base"])
        assert (base / "book" / "SUMMARY.md").exists()
        assert (base / "book" / "README.md").exists()
    finally:
        workspace_root = base_dir / f"timmy-kb-{slug}"
        if workspace_root.exists():
            shutil.rmtree(workspace_root, ignore_errors=True)
