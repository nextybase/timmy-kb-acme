# tests/test_ui_exit_buttons.py
from __future__ import annotations

import src.ui.landing_slug as landing


def test_request_shutdown_kill_path(monkeypatch) -> None:
    """Verifica che _request_shutdown provi a invocare os.kill senza ricorrere a os._exit in condizioni normali."""
    called = {"kill": False, "exit": False, "logged": False}

    class _Logger:
        def info(self, *_a, **_k):
            called["logged"] = True

    def _fake_kill(pid, sig):  # noqa: ARG001
        called["kill"] = True

    def _fake_exit(code):  # noqa: ARG001
        called["exit"] = True
        raise AssertionError("os._exit non dovrebbe essere chiamato nel percorso 'kill ok'")

    monkeypatch.setattr(landing.os, "kill", _fake_kill, raising=True)
    monkeypatch.setattr(landing.os, "_exit", _fake_exit, raising=True)

    landing._request_shutdown(_Logger())
    assert called["logged"] is True
    assert called["kill"] is True
    assert called["exit"] is False


def test_request_shutdown_fallback_exit_on_exception(monkeypatch) -> None:
    """Se os.kill fallisce, _request_shutdown deve usare il fallback os._exit."""
    called = {"kill": False, "exit": False, "logged": False}

    class _Logger:
        def info(self, *_a, **_k):
            called["logged"] = True

    def _fake_kill(pid, sig):  # noqa: ARG001
        called["kill"] = True
        raise RuntimeError("boom")

    def _fake_exit(code):  # noqa: ARG001
        called["exit"] = True

    monkeypatch.setattr(landing.os, "kill", _fake_kill, raising=True)
    monkeypatch.setattr(landing.os, "_exit", _fake_exit, raising=True)

    landing._request_shutdown(_Logger())
    assert called["logged"] is True
    assert called["kill"] is True
    assert called["exit"] is True


def test_reset_to_landing_clears_state_and_reruns(monkeypatch) -> None:
    """_reset_to_landing deve azzerare lo slug, preservare solo 'phase'/'ui.phase' e invocare rerun."""
    rerun_called = {"v": False}

    class _StubSt:
        def __init__(self):
            # stato pre-esistente
            self.session_state = {
                "phase": "something",
                landing._ui_key("phase"): "prefixed-phase",
                "slug": "acme",
                landing._ui_key("slug"): "acme",
                "random": 123,
                "another": "x",
            }

        def rerun(self):
            rerun_called["v"] = True

    stub = _StubSt()
    monkeypatch.setattr(landing, "st", stub, raising=True)

    landing._reset_to_landing()

    # slug azzerato
    assert stub.session_state.get("slug") == ""
    assert stub.session_state.get(landing._ui_key("slug")) == ""

    # chiavi preserve rimangono
    assert "phase" in stub.session_state
    assert landing._ui_key("phase") in stub.session_state

    # chiavi spurie rimosse
    assert "random" not in stub.session_state
    assert "another" not in stub.session_state

    # rerun invocato
    assert rerun_called["v"] is True
