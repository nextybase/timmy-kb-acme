# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from contextlib import nullcontext

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


def test_run_preflight_flow_skips_when_already_ok() -> None:
    st = _make_st()
    st.session_state["preflight_ok"] = True
    calls = {"run_preflight": 0}
    skip_preflight_state = {"value": False}

    def _get_skip_preflight() -> bool:
        return skip_preflight_state["value"]

    def _set_skip_preflight(value: bool) -> None:
        skip_preflight_state["value"] = value

    def _apply_preflight_once(_once_skip: bool, _session_state: dict, _logger: logging.Logger) -> bool:
        return False

    def _run_preflight():
        calls["run_preflight"] += 1
        return [], False

    onboarding_ui._run_preflight_flow(
        st,
        logger=logging.getLogger("tests.onboarding_ui"),
        get_skip_preflight=_get_skip_preflight,
        set_skip_preflight=_set_skip_preflight,
        apply_preflight_once=_apply_preflight_once,
        run_preflight=_run_preflight,
        status_guard=lambda *args, **kwargs: nullcontext(),  # type: ignore[arg-type]
    )

    assert calls["run_preflight"] == 0
    assert st._rerun_called is False


def test_run_preflight_flow_sets_flag_when_skipped_persistently() -> None:
    st = _make_st()
    calls = {"run_preflight": 0}
    skip_preflight_state = {"value": True}

    def _get_skip_preflight() -> bool:
        return skip_preflight_state["value"]

    def _set_skip_preflight(value: bool) -> None:
        skip_preflight_state["value"] = value

    def _apply_preflight_once(_once_skip: bool, _session_state: dict, _logger: logging.Logger) -> bool:
        return False

    def _run_preflight():
        calls["run_preflight"] += 1
        return [], False

    onboarding_ui._run_preflight_flow(
        st,
        logger=logging.getLogger("tests.onboarding_ui"),
        get_skip_preflight=_get_skip_preflight,
        set_skip_preflight=_set_skip_preflight,
        apply_preflight_once=_apply_preflight_once,
        run_preflight=_run_preflight,
        status_guard=lambda *args, **kwargs: nullcontext(),  # type: ignore[arg-type]
    )

    assert calls["run_preflight"] == 0
    assert st.session_state.get("preflight_ok") is True
    assert st._rerun_called is False
