# tests/test_smoke_dummy_e2e.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers.workspace_paths import local_workspace_dir

pytestmark = pytest.mark.slow


def test_gen_dummy_kb_writes_inside_tmp_path(tmp_path: Path) -> None:
    """
    Genera la KB dummy usando lo script CLI *senza* sporcare la cartella `output/`.

    Nota: usiamo l'opzione `--base-dir` dello script per indirizzare tutta la
    generazione sotto `tmp_path`, così i test restano self-contained e non
    accumulano cartelle in repository.
    """
    slug = "dummy"
    clients_db_relative = Path("clients_db/clients.yaml")
    workspace_root = local_workspace_dir(tmp_path, slug)

    # Esegui lo script con base dir forzata al tmp_path del test
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "tools.gen_dummy_kb",
        "--slug",
        slug,
        "--base-dir",
        str(tmp_path),
        "--clients-db",
        clients_db_relative.as_posix(),
    ]
    env = dict(os.environ)
    env["REPO_ROOT_DIR"] = str(repo_root)
    ret = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=repo_root, env=env)
    assert ret.returncode == 0, f"CLI fallita (rc={ret.returncode}). stdout:\n{ret.stdout}\nstderr:\n{ret.stderr}"

    # Verifica che la generazione sia avvenuta *solo* sotto tmp_path
    base = workspace_root
    assert base.is_dir(), f"Workspace non creato: {base}"

    # Percorsi minimi attesi dal generatore dummy
    book = base / "book"
    alpha = book / "alpha.md"
    beta = book / "beta.md"
    readme = book / "README.md"
    summary = book / "SUMMARY.md"

    for p in (alpha, beta, readme, summary):
        assert p.is_file(), f"File mancante: {p}"

    # Registry clienti: la dummy viene registrata nel DB locale della repo
    clients_db_file = repo_root / clients_db_relative
    assert clients_db_file.exists(), "Registry clienti non generato"
    assert "dummy" in clients_db_file.read_text(encoding="utf-8"), "Slug dummy non presente nel registry"
    assert not (base / clients_db_relative).exists(), "Registry clienti duplicato nel workspace cliente"

    # Extra: nessuna deriva su output/ (idempotenza ambientale)
    assert not (Path("output") / f"timmy-kb-{slug}").exists(), "Lo script ha sporcato output/"
