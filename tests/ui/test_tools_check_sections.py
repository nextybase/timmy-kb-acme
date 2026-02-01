# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, Iterable

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

    module.render_controls(slug="dummy", st_module=st_stub)

    assert calls["open_vision_modal"] == 1
    assert st_stub._rerun_called is True  # type: ignore[attr-defined]
    assert st_stub.session_state.get(module.SS_VISION_OPEN) is False
    assert st_stub.session_state.get(module.SS_SYS_OPEN) is False


def test_render_controls_triggers_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    st_stub.register_button_sequence("btn_open_system_prompt", [True])

    calls = _capture_calls(monkeypatch, module, "open_system_prompt_modal")

    module.render_controls(slug="dummy", st_module=st_stub)

    assert calls["open_system_prompt_modal"] == 1


def test_render_controls_runs_pdf_conversion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    st_stub.register_button_sequence("btn_pdf_to_yaml", [True])

    stub_yaml = tmp_path / "visionstatement.yaml"
    stub_yaml.write_text("ai: vision", encoding="utf-8")

    calls = {"run": 0}

    def _fake_run(*, tool_module: str, slug: str, action: str, args: Iterable[str] | None = None) -> dict[str, Any]:
        calls["run"] += 1
        return {
            "payload": {
                "status": "ok",
                "mode": "control_plane",
                "slug": slug,
                "action": action,
                "errors": [],
                "warnings": [],
                "artifacts": [str(stub_yaml)],
                "paths": {"vision_yaml": str(stub_yaml)},
                "returncode": 0,
                "timmy_beta_strict": "0",
            }
        }

    monkeypatch.setattr(module, "run_control_plane_tool", _fake_run, raising=False)

    module.render_controls(slug="dummy", st_module=st_stub)

    assert calls["run"] == 1


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


def test_render_global_entities_handles_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    sample = {
        "categories": {
            "operativi": {
                "label": "Entità operative",
                "entities": [
                    {"id": "progetto", "label": "Progetto", "document_code": "PRJ-", "examples": ["esempio"]},
                ],
            }
        }
    }
    monkeypatch.setattr(module.ontology, "load_entities", lambda: sample)

    module.render_global_entities(st_module=st_stub)


def test_render_vision_output_entities_and_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    mapping_file = tmp_path / "semantic_mapping.yaml"
    mapping_file.write_text(
        """
version: 1.0-beta
areas:
  - key: area-uno
    ambito: ambito
    descrizione_breve: breve
entities:
  - name: Progetto
    category: operativo
  - name: Fantasma
    category: oggetto
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module.ontology,
        "get_all_entities",
        lambda: [{"id": "progetto", "label": "Progetto", "document_code": "PRJ-"}],
    )

    module.render_vision_output({"mapping": str(mapping_file)}, st_module=st_stub)

    assert any("vocabolario" in msg for msg in st_stub.warning_messages)
    assert not st_stub.error_messages


def test_render_controls_calls_readme_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    module = importlib.import_module("ui.fine_tuning.tools_check_sections")

    mapping_file = tmp_path / "semantic_mapping.yaml"
    mapping_file.write_text(
        """
version: 1
areas: []
entities:
  - name: Progetto
    category: operativo
""",
        encoding="utf-8",
    )

    st_stub.session_state[module.STATE_LAST_VISION_RESULT] = {"mapping": str(mapping_file)}

    called = {"preview": 0}

    def _preview(mapping, entities_global, *, st_module=None):
        called["preview"] += 1

    monkeypatch.setattr(module, "render_readme_preview", _preview)
    monkeypatch.setattr(module.ontology, "get_all_entities", lambda: [])

    module.render_controls(slug="dummy", st_module=st_stub)

    assert called["preview"] == 1
