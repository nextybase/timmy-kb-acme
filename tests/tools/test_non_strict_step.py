# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from pathlib import Path

from tools import non_strict_step


class DummyConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_non_strict_step_records_event(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    layout = object()
    conn = DummyConn()
    events: list[dict[str, any]] = []

    monkeypatch.setattr(non_strict_step, "_open_layout", lambda slug, base_dir: layout)
    monkeypatch.setattr(non_strict_step.decision_ledger, "open_ledger", lambda layout_arg: conn)

    def fake_record_event(
        conn_arg,
        *,
        event_id: str,
        slug: str,
        event_name: str,
        actor: str,
        occurred_at: str,
        payload: dict[str, any],
    ) -> None:
        assert conn_arg is conn
        events.append(payload)

    monkeypatch.setattr(non_strict_step.decision_ledger, "record_event", fake_record_event)
    logger = logging.getLogger("tests.non_strict_step")
    with non_strict_step.non_strict_step("vision_enrichment", logger=logger, slug="dummy", base_dir=Path("dummy")):
        pass
    assert events
    assert events[0]["step"] == "vision_enrichment"


def test_non_strict_step_logs_without_layout(monkeypatch, caplog):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setattr(non_strict_step, "_open_layout", lambda slug, base_dir: None)
    captured: list[dict[str, any]] = []
    monkeypatch.setattr(non_strict_step.decision_ledger, "record_event", lambda *_, **__: captured.append({}))
    logger = logging.getLogger("tests.non_strict_step")
    caplog.set_level(logging.INFO)
    with non_strict_step.non_strict_step("prompt_tuning", logger=logger, slug="dummy", base_dir=None):
        pass
    assert "non_strict_step.no_ledger" in caplog.text
