# SPDX-License-Identifier: GPL-3.0-only
# tests/ui/test_preflight_once.py
from ui.utils.preflight_once import apply_preflight_once


class _DummyLogger:
    def __init__(self) -> None:
        self.events = []

    def info(self, name, extra=None):
        self.events.append((name, extra or {}))


def test_apply_preflight_once_sets_state_and_logs():
    ss = {}
    lg = _DummyLogger()
    used = apply_preflight_once(True, ss, lg)
    assert used is True
    assert ss.get("preflight_ok") is True
    assert ss.get("_preflight_once_applied") is True
    assert len(lg.events) == 1
    assert lg.events[0][0] == "ui.preflight.once"
    assert lg.events[0][1].get("mode") == "one_shot"


def test_apply_preflight_once_idempotent_logs_only_once():
    ss = {}
    lg = _DummyLogger()

    # Prima applicazione
    assert apply_preflight_once(True, ss, lg) is True
    assert ss.get("preflight_ok") is True
    assert len(lg.events) == 1

    # Seconda applicazione nella stessa sessione → nessun nuovo log
    assert apply_preflight_once(True, ss, lg) is True
    assert ss.get("preflight_ok") is True
    assert len(lg.events) == 1  # invariato


def test_apply_preflight_once_false_noop():
    ss = {}
    lg = _DummyLogger()
    assert apply_preflight_once(False, ss, lg) is False
    assert "preflight_ok" not in ss
    assert " _preflight_once_applied" not in ss
    assert lg.events == []
