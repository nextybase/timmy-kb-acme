# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
import sys
import types
from contextlib import nullcontext
from pathlib import Path

import pytest

from tests.ui.streamlit_like_adapter import StreamlitStubAdapter
from tests.ui.streamlit_stub import StreamlitStub
from timmy_kb.ui import onboarding_ui


def _make_st() -> StreamlitStubAdapter:
    return StreamlitStubAdapter(StreamlitStub())


def test_handle_exit_param_falsy() -> None:
    st = _make_st()
    calls = {"clear_active": 0, "clear_tab": 0}

    def _clear_active_slug(**_kwargs: object) -> None:
        calls["clear_active"] += 1

    def _clear_tab() -> None:
        calls["clear_tab"] += 1

    handled = onboarding_ui._handle_exit_param(
        st,
        logger=logging.getLogger("tests.onboarding_ui"),
        clear_active_slug=_clear_active_slug,
        clear_tab=_clear_tab,
    )

    assert handled is False
    assert calls == {"clear_active": 0, "clear_tab": 0}
    assert st._last_toast is None
    assert not st.info_messages


def test_handle_exit_param_truthy_triggers_stop() -> None:
    st = _make_st()
    st.query_params["exit"] = "1"
    calls = {"clear_active": 0, "clear_tab": 0}

    def _clear_active_slug(**_kwargs: object) -> None:
        calls["clear_active"] += 1

    def _clear_tab() -> None:
        calls["clear_tab"] += 1

    with pytest.raises(RuntimeError):
        onboarding_ui._handle_exit_param(
            st,
            logger=logging.getLogger("tests.onboarding_ui"),
            clear_active_slug=_clear_active_slug,
            clear_tab=_clear_tab,
        )

    assert calls == {"clear_active": 1, "clear_tab": 1}
    assert any("Sessione terminata" in msg for msg in st.info_messages)


def test_run_preflight_flow_skips_when_already_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    st = _make_st()
    st.session_state["preflight_ok"] = True
    calls = {"run_preflight": 0}

    monkeypatch.setattr(onboarding_ui.config_store, "get_skip_preflight", lambda **_kwargs: False, raising=True)

    def _run_preflight():
        calls["run_preflight"] += 1
        return [], False

    onboarding_ui._run_preflight_flow(
        st,
        logger=logging.getLogger("tests.onboarding_ui"),
        run_preflight=_run_preflight,
        status_guard=lambda *args, **kwargs: nullcontext(),  # type: ignore[arg-type]
        repo_root=Path("."),
    )

    assert calls["run_preflight"] == 0
    assert st._rerun_called is False


def test_run_preflight_flow_sets_flag_when_skipped_persistently(monkeypatch: pytest.MonkeyPatch) -> None:
    st = _make_st()
    calls = {"run_preflight": 0}
    monkeypatch.setattr(onboarding_ui.config_store, "get_skip_preflight", lambda **_kwargs: True, raising=True)

    def _run_preflight():
        calls["run_preflight"] += 1
        return [], False

    onboarding_ui._run_preflight_flow(
        st,
        logger=logging.getLogger("tests.onboarding_ui"),
        run_preflight=_run_preflight,
        status_guard=lambda *args, **kwargs: nullcontext(),  # type: ignore[arg-type]
        repo_root=Path("."),
    )

    assert calls["run_preflight"] == 0
    assert st.session_state.get("preflight_ok") is True
    assert st._rerun_called is False


def test_hydrate_query_defaults_missing_route_state_stops(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)

    original_import = onboarding_ui.importlib.import_module

    def _import(name: str):
        if name == "ui.utils.route_state":
            raise ImportError("missing route_state")
        return original_import(name)

    monkeypatch.setattr(onboarding_ui.importlib, "import_module", _import, raising=True)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            onboarding_ui._hydrate_query_defaults()

    assert stub.error_messages
    assert any("Router UI non disponibile" in msg for msg in stub.error_messages)
    assert any("ui.route_state.import_failed" in record.getMessage() for record in caplog.records)


def test_hydrate_query_defaults_runtime_error_stops(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)

    route_state = types.SimpleNamespace()

    def _get_tab(_default: str) -> str:
        raise RuntimeError("boom")

    route_state.get_tab = _get_tab
    route_state.get_slug_from_qp = lambda: None

    monkeypatch.setattr(
        onboarding_ui.importlib,
        "import_module",
        lambda name: route_state if name == "ui.utils.route_state" else None,
        raising=True,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            onboarding_ui._hydrate_query_defaults()

    assert stub.error_messages
    assert any("Errore nel routing UI" in msg for msg in stub.error_messages)
    assert any("ui.route_state.hydration_failed" in record.getMessage() for record in caplog.records)


def test_main_loads_env_before_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _ensure_env(*_args: object, **_kwargs: object) -> bool:
        calls.append("env")
        return True

    def _bootstrap(_repo_root) -> logging.Logger:
        calls.append("bootstrap")
        raise RuntimeError("stop")

    monkeypatch.setattr("pipeline.env_utils.ensure_dotenv_loaded", _ensure_env)
    monkeypatch.setattr(onboarding_ui, "_lazy_bootstrap", _bootstrap, raising=True)
    monkeypatch.setattr(onboarding_ui, "get_repo_root", lambda: Path("."), raising=True)

    with pytest.raises(RuntimeError):
        onboarding_ui.main()

    assert calls == ["env", "bootstrap"]
