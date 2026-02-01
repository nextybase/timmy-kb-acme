# SPDX-License-Identifier: GPL-3.0-or-later
import logging

from pipeline.logging_utils import get_structured_logger, phase_scope


class _Mem(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - trivial
        self.records.append(record)


def _logger() -> tuple[logging.Logger, _Mem]:
    lg = get_structured_logger("test.phase.structured", run_id="run-1")
    h = _Mem()
    h.setLevel(logging.INFO)
    lg.addHandler(h)
    return lg, h


def test_phase_scope_structured_success(caplog):
    lg, h = _logger()
    with phase_scope(lg, stage="s", customer="c") as m:
        m.set_artifacts(5)

    started = next(r for r in h.records if r.msg == "phase_started")
    completed = next(r for r in h.records if r.msg == "phase_completed")

    assert getattr(started, "status", None) == "start"
    assert getattr(started, "phase", None) == "s"
    assert getattr(completed, "status", None) == "success"
    assert isinstance(getattr(completed, "duration_ms", 0), int)
    # Nuovo alias strutturato
    assert getattr(completed, "artifacts", None) == 5
    # Back-compat
    assert getattr(completed, "artifact_count", None) == 5


def test_phase_scope_structured_failure_includes_error():
    lg, h = _logger()
    try:
        with phase_scope(lg, stage="boom", customer="c"):
            raise RuntimeError("xboom")
    except RuntimeError:
        pass

    failed = next(r for r in h.records if r.msg == "phase_failed")
    assert getattr(failed, "status", None) == "failed"
    assert "xboom" in str(getattr(failed, "error", ""))
