from __future__ import annotations


def test_landing_has_new_create_button_label(monkeypatch):
    import src.ui.landing_slug as landing

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _DummySt:
        def __init__(self):
            self.session_state = {
                "vision_workflow": {
                    "slug": "acme",
                    "verified": True,
                    "needs_creation": True,
                    "pdf_bytes": None,
                    "client_name": "",
                }
            }
            self.buttons: list[str] = []

        def markdown(self, *a, **k):
            return None

        def columns(self, *a, **k):
            return [_Ctx(), _Ctx(), _Ctx()]

        def text_input(self, *a, **k):
            # Return non-empty lowercase slug and a name
            return "acme"

        def button(self, label: str, *a, **k):
            self.buttons.append(label)
            return False

        def file_uploader(self, *a, **k):
            return None

        def caption(self, *a, **k):
            return None

        def success(self, *a, **k):
            return None

        def info(self, *a, **k):
            return None

    dummy = _DummySt()
    monkeypatch.setattr(landing, "st", dummy, raising=True)
    # Avoid logo side effects
    monkeypatch.setattr(landing, "_render_logo", lambda: None, raising=True)

    # Drive the rendering; ignore return values
    try:
        landing.render_landing_slug()
    except Exception:
        # Ignore issues from partial st shim
        pass

    assert any(b == "Crea workspace + carica PDF" for b in dummy.buttons), "Bottone aggiornato non trovato in landing"


def test_setup_has_inizializza_workspace_label(monkeypatch, tmp_path):
    import src.ui.app as app

    class _DummySt:
        def __init__(self):
            self.session_state = {}
            self.buttons: list[str] = []

        def header(self, *a, **k):
            return None

        def caption(self, *a, **k):
            return None

        def button(self, label: str, *a, **k):
            self.buttons.append(label)
            return False

    # Stub dependencies used in _render_setup
    monkeypatch.setattr(app, "_copy_base_config", lambda *a, **k: tmp_path / "config.yaml", raising=True)
    monkeypatch.setattr(app, "_render_config_editor", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(app, "_handle_pdf_upload", lambda *a, **k: False, raising=True)

    dummy = _DummySt()
    monkeypatch.setattr(app, "st", dummy, raising=True)

    app._render_setup("acme", tmp_path, logger=app._setup_logging())

    assert any(b == "Inizializza workspace" for b in dummy.buttons)
