from __future__ import annotations

from pathlib import Path

from pipeline.exceptions import ConfigError


class _DummySt:
    def __init__(self, trigger_button: str | None = None):
        self.session_state = {}
        self.calls: list[tuple] = []
        self._trigger_button = trigger_button

    # Basic UI shims
    def header(self, *args, **kwargs):
        self.calls.append(("header", args, kwargs))

    def subheader(self, *args, **kwargs):
        self.calls.append(("subheader", args, kwargs))

    def caption(self, text):
        self.calls.append(("caption", text))

    def info(self, text):
        self.calls.append(("info", text))

    def error(self, text):
        self.calls.append(("error", text))

    def code(self, content, language=None):
        # Traccia lingua e prefisso contenuto
        self.calls.append(("code", language, content[:32]))

    def expander(self, label: str, expanded: bool = False):
        self.calls.append(("expander", label, expanded))

        class _Ctx:
            def __enter__(self_inner):
                return self

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    def button(self, label: str, *args, **kwargs):
        self.calls.append(("button", label))
        return bool(self._trigger_button and self._trigger_button == label)


def test_debug_expander_helper_shows_files(tmp_path: Path, monkeypatch):
    import src.ui.app as app

    # Prepara workspace con file di debug
    sem = tmp_path / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    (sem / ".vision_last_response.json").write_text('{\n  "ok": true\n}', encoding="utf-8")
    (sem / ".vision_last_error.txt").write_text("Traceback: boom", encoding="utf-8")

    dummy = _DummySt()
    monkeypatch.setattr(app, "st", dummy, raising=True)

    app._render_debug_expander(tmp_path)

    # Verifica che l'expander sia stato mostrato e che abbia mostrato i due file
    exp_calls = [c for c in dummy.calls if c and c[0] == "expander" and c[1] == "Debug"]
    assert exp_calls, "Expander 'Debug' non mostrato"
    code_langs = [c[1] for c in dummy.calls if c and c[0] == "code"]
    assert "json" in code_langs and "text" in code_langs


def test_init_workspace_error_triggers_expander(tmp_path: Path, monkeypatch):
    import src.ui.app as app

    # Fake st che preme il bottone 'Inizializza workspace'
    dummy = _DummySt(trigger_button="Inizializza workspace")
    monkeypatch.setattr(app, "st", dummy, raising=True)

    # Mock dipendenze per non eseguire UI complesse
    monkeypatch.setattr(app, "_render_config_editor", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(app, "_handle_pdf_upload", lambda *a, **k: True, raising=True)

    def _raise(slug, workspace_dir, logger):
        raise ConfigError("boom")

    monkeypatch.setattr(app, "_initialize_workspace", _raise, raising=True)

    # Prepara struttura workspace con semantic/ e file debug
    sem = tmp_path / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    (sem / ".vision_last_response.json").write_text('{\n  "ok": false\n}', encoding="utf-8")

    app._render_setup("acme", tmp_path, logger=app._setup_logging())

    exp_calls = [c for c in dummy.calls if c and c[0] == "expander" and c[1] == "Debug"]
    assert exp_calls, "Expander 'Debug' non mostrato su errore inizializzazione"
