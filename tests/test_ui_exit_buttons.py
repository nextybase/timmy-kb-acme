from __future__ import annotations


def test_chiudi_app_back_to_landing_does_not_exit(monkeypatch):
    import src.ui.app as app

    class _DummySt:
        def __init__(self):
            self.session_state = {"phase": "setup", "foo": 1}

    dummy = _DummySt()
    monkeypatch.setattr(app, "st", dummy, raising=True)

    # Call: should reset to landing and drop other keys
    app._back_to_landing()
    assert dummy.session_state.get("phase") == "landing"
    assert "foo" not in dummy.session_state


def test_esci_app_calls_kill(monkeypatch):
    import src.ui.app as app

    called = {}

    def _fake_kill(pid, sig):
        called["kill"] = (pid, sig)

    def _fake_exit(code):  # guard in case of fallback
        called["exit"] = code
        raise SystemExit(code)

    monkeypatch.setattr(app.os, "kill", _fake_kill, raising=True)
    monkeypatch.setattr(app.os, "_exit", _fake_exit, raising=True)

    class _Log:
        def info(self, *args, **kwargs):
            return None

    try:
        app._request_shutdown(_Log())
    except SystemExit:
        pass

    assert "kill" in called  # ensure kill attempted


def test_chiudi_landing_resets_state(monkeypatch):
    import src.ui.landing_slug as landing

    class _DummySt:
        def __init__(self):
            self.session_state = {"slug": "x", "client_name": "y", "vision_workflow": {}}

        def rerun(self):
            return None

    dummy = _DummySt()
    monkeypatch.setattr(landing, "st", dummy, raising=True)

    landing._reset_to_landing()
    assert dummy.session_state.get("slug") == ""
    assert "client_name" not in dummy.session_state
    assert "vision_workflow" not in dummy.session_state


def test_esci_landing_calls_kill(monkeypatch):
    import src.ui.landing_slug as landing

    called = {}

    def _fake_kill(pid, sig):
        called["kill"] = (pid, sig)

    def _fake_exit(code):
        called["exit"] = code
        raise SystemExit(code)

    monkeypatch.setattr(landing.os, "kill", _fake_kill, raising=True)
    monkeypatch.setattr(landing.os, "_exit", _fake_exit, raising=True)

    try:
        landing._request_shutdown(None)
    except SystemExit:
        pass

    assert "kill" in called
