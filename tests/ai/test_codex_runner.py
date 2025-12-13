# SPDX-License-Identifier: GPL-3.0-or-later
# tests/ai/test_codex_runner.py
from __future__ import annotations

import subprocess
from pathlib import Path

from ai.codex_runner import run_codex_cli


class _DummyProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_prompt(tmp_path: Path, monkeypatch, result: object):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: result,
    )
    return run_codex_cli(
        "Fix something",
        cwd=tmp_path,
        cmd=["codex", "run"],
        timeout_s=5,
    )


def test_run_codex_cli_success_truncates(monkeypatch, tmp_path: Path) -> None:
    stdout = "x" * 210_000
    stderr = "ok"
    result = _DummyProcess(returncode=0, stdout=stdout, stderr=stderr)
    outcome = _run_prompt(tmp_path, monkeypatch, result)

    assert outcome.ok
    assert outcome.exit_code == 0
    assert outcome.stderr == stderr
    assert outcome.stdout.endswith("...[TRUNCATED]")
    assert outcome.error is None
    assert outcome.duration_ms >= 0


def test_run_codex_cli_failure_returns_ok_false(monkeypatch, tmp_path: Path) -> None:
    result = _DummyProcess(returncode=2, stdout="fail", stderr="error")
    outcome = _run_prompt(tmp_path, monkeypatch, result)

    assert not outcome.ok
    assert outcome.exit_code == 2
    assert outcome.stdout == "fail"
    assert outcome.stderr == "error"
    assert outcome.error is None


def test_run_codex_cli_timeout(monkeypatch, tmp_path: Path) -> None:
    def _raises_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=5, output="out", stderr="err")

    monkeypatch.setattr("subprocess.run", _raises_timeout)
    outcome = run_codex_cli(
        "Edit",
        cwd=tmp_path,
        cmd=["codex", "run"],
        timeout_s=5,
    )

    assert not outcome.ok
    assert outcome.exit_code == -1
    assert "timeout" in (outcome.error or "").lower()
    assert outcome.stdout == "out"
    assert outcome.stderr == "err"


def test_run_codex_cli_exception(monkeypatch, tmp_path: Path) -> None:
    def _raises_error(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr("subprocess.run", _raises_error)
    outcome = run_codex_cli(
        "Edit",
        cwd=tmp_path,
        cmd=["codex", "run"],
        timeout_s=5,
    )

    assert not outcome.ok
    assert outcome.exit_code == -1
    assert outcome.error is not None
    assert "boom" in outcome.error
    assert outcome.stdout == ""
    assert outcome.stderr == ""
