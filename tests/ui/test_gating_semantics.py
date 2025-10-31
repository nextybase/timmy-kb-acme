from __future__ import annotations

from typing import Optional

import pytest

import ui.gating as gating
from ui.gating import GateState, PagePaths, visible_page_specs


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    gating._LAST_RAW_READY.clear()


def _semantics_visible(groups: dict[str, list[gating.PageSpec]]) -> bool:
    return any(spec.path == PagePaths.SEMANTICS for specs in groups.values() for spec in specs)


@pytest.mark.parametrize(
    ("slug", "raw_ready", "expected"),
    [
        ("dummy", True, True),
        ("dummy", False, False),
        (None, False, False),
    ],
)
def test_visible_page_specs_hides_semantics_without_raw(
    slug: Optional[str], raw_ready: bool, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gating, "get_active_slug", lambda: slug, raising=False)

    def _fake_has_raw(slug_value: str) -> tuple[bool, Optional[str]]:
        assert slug_value == (slug or slug_value)
        return raw_ready, None

    monkeypatch.setattr(gating, "has_raw_pdfs", _fake_has_raw, raising=False)

    gates = GateState(drive=True, vision=True, tags=True)
    groups = visible_page_specs(gates)
    assert _semantics_visible(groups) is expected


def test_semantics_hidden_logs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyLogger:
        def __init__(self) -> None:
            self.records: list[tuple[str, dict[str, object]]] = []

        def info(self, message: str, *, extra: dict[str, object]) -> None:
            self.records.append((message, extra))

    dummy_logger = DummyLogger()
    monkeypatch.setattr(gating, "_LOGGER", dummy_logger, raising=False)
    monkeypatch.setattr(gating, "get_active_slug", lambda: "dummy", raising=False)
    monkeypatch.setattr(gating, "has_raw_pdfs", lambda _slug: (False, None), raising=False)

    gates = GateState(drive=True, vision=True, tags=True)
    visible_page_specs(gates)
    visible_page_specs(gates)  # seconda invocazione: nessun log addizionale

    assert len(dummy_logger.records) == 1
    message, extra = dummy_logger.records[0]
    assert message == "ui.gating.sem_hidden"
    assert extra["slug"] == "dummy"
