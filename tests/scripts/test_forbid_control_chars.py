# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import shutil
import subprocess
import sys
import unicodedata
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "forbid_control_chars.py"


@pytest.fixture()
def repo_tmp() -> Path:
    base = REPO_ROOT / "tests" / "_tmp_forbid"
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"case_{uuid.uuid4().hex}"
    target.mkdir(parents=True, exist_ok=True)
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)


def run_hook(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_detects_control_chars_without_fix(repo_tmp: Path) -> None:
    target = repo_tmp / "bad.txt"
    target.write_text("Hello\x01World", encoding="utf-8")

    relative = target.relative_to(REPO_ROOT)
    result = run_hook(str(relative))

    assert result.returncode == 1
    assert "controll" in result.stdout.lower()


def test_fix_removes_controls_and_normalizes(repo_tmp: Path) -> None:
    text = "caf\u00a9\x02\u0065\u0301"
    target = repo_tmp / "fix.txt"
    target.write_text(text, encoding="utf-8")

    relative = target.relative_to(REPO_ROOT)
    result = run_hook("--fix", str(relative))
    assert result.returncode == 0

    updated = target.read_text(encoding="utf-8")
    assert "\x02" not in updated
    assert unicodedata.normalize("NFC", updated) == updated
    assert updated == "caf©é"

    result_check = run_hook(str(relative))
    assert result_check.returncode == 0
