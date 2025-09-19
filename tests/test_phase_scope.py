import logging

from pipeline.logging_utils import get_structured_logger, phase_scope


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - trivial
        self.records.append(record)


def _capture_logger(name: str = "test.phase") -> tuple[logging.Logger, _ListHandler]:
    lg = get_structured_logger(name, run_id="run-test")
    h = _ListHandler()
    h.setLevel(logging.INFO)
    lg.addHandler(h)
    return lg, h


def test_phase_scope_success_emits_started_and_completed():
    logger, handler = _capture_logger()

    with phase_scope(logger, stage="unit_test", customer="acme") as m:
        m.set_artifacts(3)

    msgs = [r.msg for r in handler.records]
    assert "phase_started" in msgs
    assert "phase_completed" in msgs

    started = next(r for r in handler.records if r.msg == "phase_started")
    completed = next(r for r in handler.records if r.msg == "phase_completed")

    assert getattr(started, "event", None) == "phase_started"
    assert getattr(started, "phase", None) == "unit_test"
    assert getattr(started, "slug", None) == "acme"
    assert getattr(started, "run_id", None) == "run-test"

    assert getattr(completed, "event", None) == "phase_completed"
    assert getattr(completed, "phase", None) == "unit_test"
    assert isinstance(getattr(completed, "duration_ms", 0), int)
    assert getattr(completed, "artifact_count", None) == 3


def test_phase_scope_failure_emits_failed(monkeypatch):
    logger, handler = _capture_logger()

    try:
        with phase_scope(logger, stage="failing", customer="acme"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    msgs = [r.msg for r in handler.records]
    assert "phase_started" in msgs
    assert "phase_failed" in msgs
