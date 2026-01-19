# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import logging
import sys
from typing import Optional

import pytest

import ui.gating as gating
from tests.ui.streamlit_stub import StreamlitStub
from ui.gating import GateState, PagePaths, visible_page_specs


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    gating.reset_gating_cache()


def _semantics_visible(groups: dict[str, list[gating.PageSpec]]) -> bool:
    return any(spec.path == PagePaths.SEMANTICS for specs in groups.values() for spec in specs)


@pytest.mark.parametrize(
    ("slug", "raw_ready", "tagging_ready", "expected"),
    [
        ("dummy", True, True, True),
        ("dummy", False, True, False),
        ("dummy", True, False, False),
        (None, False, False, False),
    ],
)
def test_visible_page_specs_hides_semantics_without_raw_or_tagging(
    slug: Optional[str], raw_ready: bool, tagging_ready: bool, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gating, "get_active_slug", lambda: slug, raising=False)

    def _fake_raw_ready(slug_value: str, **_kwargs: object) -> tuple[bool, Optional[str]]:
        assert slug_value == (slug or slug_value)
        return raw_ready, None

    def _fake_tagging_ready(slug_value: str, **_kwargs: object) -> tuple[bool, Optional[str]]:
        assert slug_value == (slug or slug_value)
        return tagging_ready, None

    monkeypatch.setattr(gating, "raw_ready", _fake_raw_ready, raising=False)
    monkeypatch.setattr(gating, "tagging_ready", _fake_tagging_ready, raising=False)

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
    monkeypatch.setattr(gating, "raw_ready", lambda _slug, **_kwargs: (False, None), raising=False)
    monkeypatch.setattr(gating, "tagging_ready", lambda _slug, **_kwargs: (False, None), raising=False)

    gates = GateState(drive=True, vision=True, tags=True)
    visible_page_specs(gates)
    visible_page_specs(gates)  # seconda invocazione: nessun log addizionale

    sem_logs = [extra for message, extra in dummy_logger.records if message == "ui.gating.sem_hidden"]
    assert len(sem_logs) == 1
    assert sem_logs[0]["slug"] == "dummy"


def test_compute_gates_disables_missing_services(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Optional[str]] = {}

    def _fake_available(module_name: str, *, attr: Optional[str] = None) -> bool:
        calls[module_name] = attr
        return module_name != "ui.services.drive_runner"

    monkeypatch.setattr(gating, "_module_available", _fake_available, raising=False)

    gates = gating.compute_gates({})

    assert gates.drive is False
    assert gates.vision is True
    assert gates.tags is True
    assert calls["ui.services.drive_runner"] == "plan_raw_download"
    assert calls["ui.services.vision_provision"] == "run_vision"
    assert calls["ui.services.tags_adapter"] == "run_tags_update"


def test_gate_capability_manifest_written_and_valid(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_available(module_name: str, *, attr: Optional[str] = None) -> bool:
        return True

    monkeypatch.setattr(gating, "_module_available", _fake_available, raising=False)

    payload = gating.write_gate_capability_manifest(tmp_path)
    path = tmp_path / "gate_capabilities.json"
    assert path.exists()
    stored = json.loads(path.read_text(encoding="utf-8"))

    for data in (payload, stored):
        assert data["schema_version"] == 1
        assert isinstance(data["computed_at"], str)
        gates = data["gates"]
        assert set(gates.keys()) == {"drive", "vision", "tags", "qa"}
        assert gates["qa"]["available"] is True


def test_gate_capability_manifest_matches_compute_gates(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_available(module_name: str, *, attr: Optional[str] = None) -> bool:
        return module_name != "ui.services.drive_runner"

    env = {"DRIVE": "1", "VISION": "0", "TAGS": "1"}
    monkeypatch.setattr(gating, "_module_available", _fake_available, raising=False)

    payload = gating.write_gate_capability_manifest(tmp_path, env=env)
    gates = gating.compute_gates(env)

    assert payload["gates"]["drive"]["available"] == gates.drive
    assert payload["gates"]["vision"]["available"] == gates.vision
    assert payload["gates"]["tags"]["available"] == gates.tags


def test_visible_page_specs_continues_on_raw_ready_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    monkeypatch.setattr(gating, "get_active_slug", lambda: "dummy", raising=False)
    monkeypatch.setattr(gating, "raw_ready", lambda _slug, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    gates = GateState(drive=True, vision=True, tags=True)
    with caplog.at_level(logging.ERROR):
        groups = visible_page_specs(gates)

    assert any("ui.gating.raw_ready_failed" in record.getMessage() for record in caplog.records)
    assert groups


def test_visible_page_specs_continues_on_state_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    monkeypatch.setattr(gating, "get_active_slug", lambda: "dummy", raising=False)
    monkeypatch.setattr(gating, "raw_ready", lambda _slug, **_kwargs: (True, None), raising=False)
    monkeypatch.setattr(gating, "tagging_ready", lambda _slug, **_kwargs: (True, None), raising=False)
    monkeypatch.setattr(gating, "get_state", lambda _slug: (_ for _ in ()).throw(RuntimeError("boom")))

    gates = GateState(drive=True, vision=True, tags=True)
    with caplog.at_level(logging.ERROR):
        groups = visible_page_specs(gates)

    assert any("ui.gating.state_failed" in record.getMessage() for record in caplog.records)
    assert groups
