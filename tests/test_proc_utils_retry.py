# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import subprocess

import pytest

from pipeline import proc_utils
from pipeline.proc_utils import CmdContext, CmdError, cmd_attempt, retry_loop

pytestmark = pytest.mark.unit


class DummyLogger:
    def __init__(self) -> None:
        self.records = []

    def debug(self, *_args, **kwargs) -> None:  # noqa: D401 - test helper
        self.records.append(("debug", kwargs))

    def info(self, *_args, **kwargs) -> None:
        self.records.append(("info", kwargs))

    def warning(self, *_args, **kwargs) -> None:
        self.records.append(("warning", kwargs))

    def error(self, *_args, **kwargs) -> None:
        self.records.append(("error", kwargs))


def _context(**overrides: object) -> CmdContext:
    base = dict(
        argv=("echo", "hello"),
        op="echo",
        attempts=2,
        timeout_s=1.0,
        cwd=None,
        cwd_log="",
        env={},
        capture=True,
        redactor=lambda s: s,
        logger=None,
        backoff=1.5,
    )
    base.update(overrides)
    return CmdContext(**base)


def test_cmd_attempt_success(monkeypatch):
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(proc_utils.subprocess, "run", fake_run)
    ctx = _context()
    result = cmd_attempt(ctx, attempt=1)
    assert result.returncode == 0
    assert result.stdout == "ok"


def test_cmd_attempt_timeout(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])

    monkeypatch.setattr(proc_utils.subprocess, "run", fake_run)
    ctx = _context()
    with pytest.raises(CmdError) as exc:
        cmd_attempt(ctx, attempt=1)
    assert exc.value.timeout is True


def test_retry_loop_succeeds_after_retry(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return subprocess.CompletedProcess(argv, 1, stdout="first", stderr="err")
        return subprocess.CompletedProcess(argv, 0, stdout="second", stderr="")

    monkeypatch.setattr(proc_utils.subprocess, "run", fake_run)
    monkeypatch.setattr(proc_utils.time, "sleep", lambda _x: None)
    ctx = _context()
    result = retry_loop(ctx)
    assert result.returncode == 0
    assert len(calls) == 2


def test_retry_loop_exhausts_attempts(monkeypatch):
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="bad", stderr="nope")

    monkeypatch.setattr(proc_utils.subprocess, "run", fake_run)
    monkeypatch.setattr(proc_utils.time, "sleep", lambda _x: None)
    ctx = _context()
    with pytest.raises(CmdError):
        retry_loop(ctx)


def test_run_cmd_integration(monkeypatch):
    sequence = iter(
        [
            subprocess.CompletedProcess(["cmd"], 1, stdout="first", stderr="err"),
            subprocess.CompletedProcess(["cmd"], 0, stdout="ok", stderr=""),
        ]
    )

    def fake_run(argv, **kwargs):
        return next(sequence)

    logger = DummyLogger()
    monkeypatch.setattr(proc_utils.subprocess, "run", fake_run)
    monkeypatch.setattr(proc_utils.time, "sleep", lambda _x: None)
    result = proc_utils.run_cmd(["cmd"], retries=1, logger=logger, capture=True)
    assert result.returncode == 0
    # ensure at least one retry happened (two info records)
    assert any(level == "warning" for level, _ in logger.records)
