# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_ui_safe_rerun.py
from __future__ import annotations

import ui.landing_slug as landing


def test_safe_rerun_noop_when_missing(monkeypatch) -> None:
    # Se Streamlit non è disponibile, la funzione non deve esplodere
    monkeypatch.setattr(landing, "st", None, raising=True)
    landing._safe_rerun()  # no exception


def test_safe_rerun_calls_rerun(monkeypatch) -> None:
    called: dict[str, bool] = {}

    class _Stub:
        def rerun(self) -> None:
            called["run"] = True

    monkeypatch.setattr(landing, "st", _Stub(), raising=True)
    landing._safe_rerun()
    assert called.get("run") is True


def test_safe_rerun_ignores_internal_exceptions(monkeypatch) -> None:
    class _Stub:
        def rerun(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(landing, "st", _Stub(), raising=True)
    # Non deve propagare eccezioni interne
    landing._safe_rerun()
