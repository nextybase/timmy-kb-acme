# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict

import pytest

MATRIX = [
    {"DRIVE": "0", "VISION": "0", "TAGS": "0"},
    {"DRIVE": "1", "VISION": "0", "TAGS": "0"},
    {"DRIVE": "1", "VISION": "1", "TAGS": "0"},
    {"DRIVE": "1", "VISION": "1", "TAGS": "1"},
]

THIS_DIR = Path(__file__).resolve().parent
SNAPSHOT_DIR = THIS_DIR / "snapshots"
REPO_ROOT = THIS_DIR.parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "ci_dump_nav.py"


def _snapshot_name(env: Dict[str, str]) -> str:
    return f"nav_contract_{env['DRIVE']}{env['VISION']}{env['TAGS']}.json"


def _load_snapshot(env: Dict[str, str]) -> dict:
    path = SNAPSHOT_DIR / _snapshot_name(env)
    if not path.exists():
        raise AssertionError(f"Snapshot mancante: {path}. Rigenera con tools/ci_dump_nav.py e verifica la PR.")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.contract
@pytest.mark.parametrize("env", MATRIX, ids=_snapshot_name)
def test_navigation_contract(env: Dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    output = subprocess.check_output(
        [sys.executable, str(SCRIPT_PATH)],
        text=True,
        cwd=REPO_ROOT,
    )
    start = output.find("{")
    assert start >= 0, "Output JSON non trovato in tools/ci_dump_nav.py"
    actual = json.loads(output[start:])
    expected = _load_snapshot(env)
    assert actual == expected
