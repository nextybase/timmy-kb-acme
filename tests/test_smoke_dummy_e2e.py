# tests/test_smoke_dummy_e2e.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def test_gen_dummy_kb_writes_inside_tmp_path(tmp_path: Path) -> None:
    """
    Genera la KB dummy usando lo script CLI *senza* sporcare la cartella `output/`.

    Nota: usiamo l'opzione `--base-dir` dello script per indirizzare tutta la
    generazione sotto `tmp_path`, così i test restano self-contained e non
    accumulano cartelle in repository.
    """
    slug = f"dummy-{int(time.time())}"

    # Esegui lo script con base dir forzata al tmp_path del test
    cmd = [
        sys.executable,
        "src/tools/gen_dummy_kb.py",
        "--slug",
        slug,
        "--base-dir",
        str(tmp_path),
    ]
    ret = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert ret.returncode == 0, f"CLI fallita (rc={ret.returncode}). stdout:\n{ret.stdout}\nstderr:\n{ret.stderr}"

    # Verifica che la generazione sia avvenuta *solo* sotto tmp_path
    base = tmp_path / f"timmy-kb-{slug}"
    assert base.is_dir(), f"Workspace non creato: {base}"

    # Percorsi minimi attesi dal generatore dummy
    book = base / "book"
    alpha = book / "alpha.md"
    beta = book / "beta.md"
    readme = book / "README.md"
    summary = book / "SUMMARY.md"

    for p in (alpha, beta, readme, summary):
        assert p.is_file(), f"File mancante: {p}"

    # Extra: nessuna deriva su output/ (idempotenza ambientale)
    assert not (Path("output") / f"timmy-kb-{slug}").exists(), "Lo script ha sporcato output/"
