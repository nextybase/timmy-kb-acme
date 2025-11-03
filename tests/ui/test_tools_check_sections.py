# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.ui.stub_helpers import install_streamlit_stub


def _capture_calls(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> Dict[str, int]:
    calls = {name: 0}

    def _record(*_args: Any, **_kwargs: Any) -> None:
        calls[name] += 1

    monkeypatch.setattr(module, name, _record, raising=False)
    return calls


def test_render_controls_triggers_vision_modal(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    st_stub.session_state.clear()
    st_stub.register_button_sequence("btn_open_vision_modal", [True])

    calls = _capture_calls(monkeypatch, module, "open_vision_modal")

    module.render_controls(slug="acme", st_module=st_stub)

    assert calls["open_vision_modal"] == 1
    assert st_stub._rerun_called is True  # type: ignore[attr-defined]
    assert st_stub.session_state.get(module.SS_VISION_OPEN) is False
    assert st_stub.session_state.get(module.SS_SYS_OPEN) is False


def test_render_controls_triggers_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    st_stub.register_button_sequence("btn_open_system_prompt", [True])

    calls = _capture_calls(monkeypatch, module, "open_system_prompt_modal")

    module.render_controls(slug="acme", st_module=st_stub)

    assert calls["open_system_prompt_modal"] == 1


def test_render_controls_runs_pdf_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    st_stub.register_button_sequence("btn_pdf_to_yaml", [True])

    calls = _capture_calls(monkeypatch, module, "run_pdf_to_yaml_config")

    module.render_controls(slug="acme", st_module=st_stub)

    assert calls["run_pdf_to_yaml_config"] == 1


def test_render_vision_output_reads_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")
    captured: list[Dict[str, Any]] = []
    st_stub.json = lambda payload: captured.append(payload)  # type: ignore[attr-defined]

    mapping_file = tmp_path / "semantic_mapping.yaml"
    mapping_file.write_text(
        """
version: 1.0-beta
areas:
  - key: governance
    ambito: governance
    descrizione_breve: breve
    descrizione_dettagliata:
      include: ["doc1"]
metadata_policy:
  chunk_length_tokens:
    target: 500
""",
        encoding="utf-8",
    )

    module.render_vision_output({"mapping": str(mapping_file)}, st_module=st_stub)

    assert captured, "Atteso JSON con il mapping caricato."
    assert captured[-1]["version"] == "1.0-beta"


def test_render_vision_output_fallbacks_to_raw_result(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")
    captured: list[Any] = []
    st_stub.json = lambda payload: captured.append(payload)  # type: ignore[attr-defined]

    raw_result = {"status": "halt", "message_ui": "Missing data"}
    module.render_vision_output(raw_result, st_module=st_stub)

    assert captured == [raw_result]


def test_render_advanced_options_clears_state(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")
    st_stub.session_state.update({"ft_value": 1, "_SS_FLAG": True, "other": "keep"})
    st_stub.register_button_sequence("btn_reset_state", [True])

    module.render_advanced_options(st_module=st_stub)

    assert "ft_value" not in st_stub.session_state
    assert "_SS_FLAG" not in st_stub.session_state
    assert st_stub.session_state["other"] == "keep"
    assert "Stato ripulito." in st_stub.success_messages
