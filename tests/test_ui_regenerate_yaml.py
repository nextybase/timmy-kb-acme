from __future__ import annotations

from pathlib import Path
from typing import Tuple


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


def _override_yaml(workspace: dict[str, Path], *, mapping_text: str, cartelle_text: str) -> Tuple[str, str]:
    mapping = workspace["semantic_mapping"]
    cartelle = workspace["cartelle_raw"]
    original_mapping = mapping.read_text(encoding="utf-8")
    original_cartelle = cartelle.read_text(encoding="utf-8")
    mapping.write_text(mapping_text, encoding="utf-8")
    cartelle.write_text(cartelle_text, encoding="utf-8")
    return original_mapping, original_cartelle


def test_regenerate_requires_confirmation(dummy_workspace, dummy_logger, monkeypatch):
    import src.ui.app as app

    base = dummy_workspace["base"]
    mapping_path = dummy_workspace["semantic_mapping"]
    cartelle_path = dummy_workspace["cartelle_raw"]
    slug = dummy_workspace["slug"]
    original_mapping, original_cartelle = _override_yaml(
        dummy_workspace,
        mapping_text="context:\n  slug: old\n",
        cartelle_text="version: 1\nfolders: []\n",
    )

    try:
        init = {
            "yaml_paths": {
                "mapping": str(mapping_path),
                "cartelle_raw": str(cartelle_path),
            }
        }

        dummy = _DummySt(click_regenera=True, confirm=False)
        dummy.session_state["init_result"] = init
        monkeypatch.setattr(app, "st", dummy, raising=True)

        called = {"n": 0}

        def _fake_provision(ctx, logger, *, slug, pdf_path, model="", force=False):
            called["n"] += 1
            mapping_path.write_text("context:\n  slug: new\n", encoding="utf-8")
            return {"yaml_paths": init["yaml_paths"]}

        monkeypatch.setattr(app, "provision_from_vision", _fake_provision, raising=True)

        app._render_ready(slug, base, logger=dummy_logger)

        assert called["n"] == 0
        content = mapping_path.read_text(encoding="utf-8")
        assert "old" in content
    finally:
        mapping_path.write_text(original_mapping, encoding="utf-8")
        cartelle_path.write_text(original_cartelle, encoding="utf-8")


def test_regenerate_overwrites_on_confirmation(dummy_workspace, dummy_logger, monkeypatch):
    import src.ui.app as app

    base = dummy_workspace["base"]
    mapping_path = dummy_workspace["semantic_mapping"]
    cartelle_path = dummy_workspace["cartelle_raw"]
    slug = dummy_workspace["slug"]
    original_mapping, original_cartelle = _override_yaml(
        dummy_workspace,
        mapping_text="context:\n  slug: old\n",
        cartelle_text="version: 1\nfolders: []\n",
    )

    try:
        init = {
            "yaml_paths": {
                "mapping": str(mapping_path),
                "cartelle_raw": str(cartelle_path),
            }
        }

        dummy = _DummySt(click_regenera=True, confirm=True)
        dummy.session_state["init_result"] = init
        monkeypatch.setattr(app, "st", dummy, raising=True)

        def _fake_provision(ctx, logger, *, slug, pdf_path, model="", force=False):
            mapping_path.write_text("context:\n  slug: new\n", encoding="utf-8")
            return {"yaml_paths": init["yaml_paths"]}

        monkeypatch.setattr(app, "provision_from_vision", _fake_provision, raising=True)

        app._render_ready(slug, base, logger=dummy_logger)

        content = mapping_path.read_text(encoding="utf-8")
        assert "new" in content
    finally:
        mapping_path.write_text(original_mapping, encoding="utf-8")
        cartelle_path.write_text(original_cartelle, encoding="utf-8")
