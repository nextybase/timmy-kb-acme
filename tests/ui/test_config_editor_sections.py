# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import types
from typing import Any, Dict

import pytest

from tests.ui.stub_helpers import install_streamlit_stub


def _import_module(monkeypatch: pytest.MonkeyPatch):
    stub = install_streamlit_stub(monkeypatch)
    import importlib

    module = importlib.import_module("ui.pages.config_editor")
    return module, stub


def test_render_body_collects_form_values(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _import_module(monkeypatch)

    st_stub.session_state.update(
        {
            "Engine": "assistant-beta",
            "Model": "gpt-test",
            "Strict output": False,
            "Candidate limit": 1500,
            "Budget latenza (ms)": 250,
            "Auto per budget": True,
            "Percorso file log": "logs/custom.log",
            "Log max bytes": 20480,
            "Numero backup log": 7,
            "Salta preflight iniziale": True,
            "Modalità debug": True,
            "Immagine Docker GitBook/HonKit": "repo/image:latest",
            "Workspace GitBook": "ws-01",
        }
    )
    st_stub.register_button_sequence("Salva modifiche", [True])

    data = {
        "log_file_path": "logs/onboarding.log",
        "log_max_bytes": 1048576,
        "log_backup_count": 3,
        "debug": False,
        "gitbook_image": "",
        "gitbook_workspace": "",
    }
    vision_cfg = {"engine": "assistant", "model": "gpt", "strict_output": True}
    retriever_cfg = {"candidate_limit": 1000, "latency_budget_ms": 200, "auto_by_budget": False}
    ui_cfg = {"skip_preflight": False}

    submitted, values = module.render_body(
        st_module=st_stub,
        data=data,
        vision_cfg=vision_cfg,
        retriever_cfg=retriever_cfg,
        ui_cfg=ui_cfg,
        assistant_env="OBNEXT_ASSISTANT_ID",
    )

    assert submitted is True
    assert values["vision_engine"] == "assistant-beta"
    assert values["vision_model"] == "gpt-test"
    assert values["vision_strict"] is False
    assert values["candidate_limit"] == 1500
    assert values["latency_budget"] == 250
    assert values["auto_by_budget"] is True
    assert values["log_file_path"] == "logs/custom.log"
    assert values["log_max_bytes"] == 20480
    assert values["log_backup_count"] == 7
    assert values["skip_preflight"] is True
    assert values["debug_mode"] is True
    assert values["gitbook_image"] == "repo/image:latest"
    assert values["gitbook_workspace"] == "ws-01"


def test_handle_actions_reports_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _import_module(monkeypatch)
    st_stub.session_state.clear()

    calls: Dict[str, Any] = {}
    monkeypatch.setattr(module, "update_config_with_drive_ids", lambda *a, **k: calls.update(called=True))

    ctx = types.SimpleNamespace(logger=None)

    result = module.handle_actions(
        ctx,
        st_module=st_stub,
        data={},
        vision_cfg={},
        retriever_cfg={},
        ui_cfg={},
        form_values={
            "vision_engine": "",
            "vision_model": "",
            "vision_strict": True,
            "candidate_limit": 1000,
            "latency_budget": 200,
            "auto_by_budget": False,
            "log_file_path": "logs/onboarding.log",
            "log_max_bytes": 1048576,
            "log_backup_count": 3,
            "skip_preflight": False,
            "debug_mode": False,
            "gitbook_image": "",
            "gitbook_workspace": "",
        },
    )

    assert result is False
    assert "called" not in calls
    assert any("Vision" in msg for msg in st_stub.error_messages)


def test_handle_actions_updates_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _import_module(monkeypatch)
    st_stub.session_state.clear()
    st_stub.register_button_sequence("Salva modifiche", [True])

    captured: Dict[str, Any] = {}

    def _fake_update(ctx: Any, updates: Dict[str, Any], **kwargs: Any) -> None:
        captured["updates"] = updates
        captured["ctx"] = ctx

    monkeypatch.setattr(module, "update_config_with_drive_ids", _fake_update)

    ctx = types.SimpleNamespace(logger=None)
    data = {"skip_preflight": False}
    vision_cfg = {"engine": "assistant", "model": "gpt", "strict_output": True}
    retriever_cfg = {"candidate_limit": 1000, "latency_budget_ms": 200, "auto": False}
    ui_cfg = {"skip_preflight": False}

    form_values = {
        "vision_engine": "assistant-beta",
        "vision_model": "gpt-test",
        "vision_strict": False,
        "candidate_limit": 1500,
        "latency_budget": 250,
        "auto_by_budget": True,
        "log_file_path": "logs/custom.log",
        "log_max_bytes": 20480,
        "log_backup_count": 5,
        "skip_preflight": True,
        "debug_mode": True,
        "gitbook_image": "repo/image:latest",
        "gitbook_workspace": "ws-01",
    }

    result = module.handle_actions(
        ctx,
        st_module=st_stub,
        data=data,
        vision_cfg=vision_cfg,
        retriever_cfg=retriever_cfg,
        ui_cfg=ui_cfg,
        form_values=form_values,
    )

    assert result is True
    assert captured["updates"]["vision"]["engine"] == "assistant-beta"
    assert captured["updates"]["retriever"]["candidate_limit"] == 1500
    assert captured["updates"]["ui"]["skip_preflight"] is True
    assert st_stub.session_state["config_editor_saved"] is True
    assert st_stub._rerun_called is True  # type: ignore[attr-defined]
