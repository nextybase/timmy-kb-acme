# SPDX-License-Identifier: GPL-3.0-only
# tests/test_proc_run_cmd_redacts_output.py
from __future__ import annotations

import logging
from typing import Any

import pytest
from tests.conftest import DUMMY_SLUG

from pipeline.logging_utils import get_structured_logger
from pipeline.proc_utils import CmdError, run_cmd


def test_run_cmd_redacts_output_in_fail_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    # Falsifichiamo subprocess.run per restituire un CompletedProcess con returncode != 0
    class _CP:
        def __init__(self) -> None:
            self.args: list[str] = ["dummy"]
            self.returncode: int = 1
            self.stdout: str = "Authorization: Bearer SECRET"
            self.stderr: str = "x-access-token: TOPSECRET"

    def _fake_run(argv, **kwargs) -> Any:
        return _CP()

    import pipeline.proc_utils as proc_utils

    monkeypatch.setattr(proc_utils.subprocess, "run", _fake_run, raising=True)

    # Logger strutturato con redazione attiva
    class Ctx:
        slug = DUMMY_SLUG
        redact_logs = True

    lg = get_structured_logger("tests.proc", context=Ctx(), level=logging.DEBUG)

    # Catturiamo i log WARNING del nostro logger
    with caplog.at_level(logging.WARNING, logger="tests.proc"):
        with pytest.raises(CmdError):
            run_cmd(["dummy"], retries=0, capture=True, logger=lg, op="git push")

    # Cerchiamo il record 'run_cmd.fail' e verifichiamo i tail redatti
    fail_records = [r for r in caplog.records if r.name == "tests.proc" and r.getMessage() == "run_cmd.fail"]
    assert fail_records, "Record 'run_cmd.fail' non trovato"
    rec = fail_records[-1]

    # I tail devono essere stati redatti (sia dal redactor interno sia dal filtro logger)
    assert hasattr(rec, "stdout_tail") and "Bearer ***" in rec.stdout_tail
    assert hasattr(rec, "stderr_tail") and "x-access-token:***" in rec.stderr_tail
    assert "SECRET" not in rec.stdout_tail
    assert "TOPSECRET" not in rec.stderr_tail
