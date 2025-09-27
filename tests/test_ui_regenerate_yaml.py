from __future__ import annotations

from pathlib import Path


class _DummySt:
    def __init__(self, *, click_regenera: bool, confirm: bool):
        self.session_state = {}
        self._click_regenera = click_regenera
        self._confirm = confirm
        self.calls: list[tuple] = []

    def header(self, *a, **k):
        self.calls.append(("header", a, k))

    def success(self, msg):
        self.calls.append(("success", msg))

    def json(self, data, expanded=False):
        self.calls.append(("json", data, expanded))

    def checkbox(self, label, key=None, value=False):
        self.calls.append(("checkbox", label))
        return self._confirm

    def button(self, label, *a, **k):
        self.calls.append(("button", label))
        if label == "Rigenera YAML":
            return self._click_regenera
        return False

    def warning(self, msg):
        self.calls.append(("warning", msg))

    def error(self, msg):
        self.calls.append(("error", msg))


def _write_initial_yaml(base: Path):
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    (sem / "semantic_mapping.yaml").write_text("context:\n  slug: old\n", encoding="utf-8")
    (sem / "cartelle_raw.yaml").write_text("version: 1\nfolders: []\n", encoding="utf-8")


def test_regenerate_requires_confirmation(tmp_path: Path, monkeypatch):
    import src.ui.app as app

    # Workspace con YAML esistenti e PDF
    base = tmp_path / "output" / "timmy-kb-sample"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "VisionStatement.pdf").write_bytes(b"%PDF dummy")
    _write_initial_yaml(base)

    # Stato init_result come da ready
    init = {
        "yaml_paths": {
            "mapping": str(base / "semantic" / "semantic_mapping.yaml"),
            "cartelle_raw": str(base / "semantic" / "cartelle_raw.yaml"),
        }
    }

    dummy = _DummySt(click_regenera=True, confirm=False)
    dummy.session_state["init_result"] = init
    monkeypatch.setattr(app, "st", dummy, raising=True)

    # provision finto: se chiamato, scrive contenuto "new"
    called = {"n": 0}

    def _fake_provision(ctx, logger, *, slug, pdf_path, model="", force=False):
        called["n"] += 1
        (base / "semantic" / "semantic_mapping.yaml").write_text("context:\n  slug: new\n", encoding="utf-8")
        return {"yaml_paths": init["yaml_paths"]}

    monkeypatch.setattr(app, "provision_from_vision", _fake_provision, raising=True)

    app._render_ready("sample", base, logger=app._setup_logging())

    # Niente conferma => nessuna chiamata e contenuto invariato
    assert called["n"] == 0
    content = (base / "semantic" / "semantic_mapping.yaml").read_text(encoding="utf-8")
    assert "old" in content


def test_regenerate_overwrites_on_confirmation(tmp_path: Path, monkeypatch):
    import src.ui.app as app

    base = tmp_path / "output" / "timmy-kb-sample"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "VisionStatement.pdf").write_bytes(b"%PDF dummy")
    _write_initial_yaml(base)

    init = {
        "yaml_paths": {
            "mapping": str(base / "semantic" / "semantic_mapping.yaml"),
            "cartelle_raw": str(base / "semantic" / "cartelle_raw.yaml"),
        }
    }

    dummy = _DummySt(click_regenera=True, confirm=True)
    dummy.session_state["init_result"] = init
    monkeypatch.setattr(app, "st", dummy, raising=True)

    def _fake_provision(ctx, logger, *, slug, pdf_path, model="", force=False):
        (base / "semantic" / "semantic_mapping.yaml").write_text("context:\n  slug: new\n", encoding="utf-8")
        return {"yaml_paths": init["yaml_paths"]}

    monkeypatch.setattr(app, "provision_from_vision", _fake_provision, raising=True)

    app._render_ready("sample", base, logger=app._setup_logging())

    content = (base / "semantic" / "semantic_mapping.yaml").read_text(encoding="utf-8")
    assert "new" in content
