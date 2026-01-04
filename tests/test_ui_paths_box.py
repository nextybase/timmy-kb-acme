# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_landing_shows_absolute_paths_after_provision(monkeypatch, tmp_path: Path):
    import ui.landing_slug as landing

    # Prepara workspace
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    # Finti path YAML
    mapping = base / "semantic" / "semantic_mapping.yaml"
    cartelle = base / "semantic" / "cartelle_raw.yaml"
    mapping.write_text("context:\n  slug: x\n", encoding="utf-8")
    cartelle.write_text("version: 1\nfolders: []\n", encoding="utf-8")

    class _DummyCtx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

    class _DummySt:
        def __init__(self):
            self.session_state = {
                "vision_workflow": {
                    "slug": "dummy",
                    "verified": True,
                    "needs_creation": True,
                    "pdf_bytes": b"%PDF",
                    "client_name": "Dummy",
                }
            }
            self.buttons: list[str] = []
            self.json_calls: list[dict[str, Any]] = []

        def markdown(self, *a, **k):
            return None

        def columns(self, *a, **k):
            class _Ctx:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return [_Ctx(), _Ctx(), _Ctx()]

        def text_input(self, *a, **k):
            return "dummy"

        def form(self, *a, **k):
            class _Form:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Form()

        def form_submit_button(self, *a, **k):
            return False

        def button(self, label: str, *a, **k):
            self.buttons.append(label)
            # Attiva solo il bottone di creazione
            return label == "Crea workspace + carica PDF"

        def file_uploader(self, *a, **k):
            return None

        def caption(self, *a, **k):
            return None

        def success(self, *a, **k):
            return None

        def info(self, *a, **k):
            return None

        def json(self, data, expanded=False):
            # Traccia il contenuto del box percorsi
            if isinstance(data, dict):
                self.json_calls.append(data)

    dummy = _DummySt()
    monkeypatch.setattr(landing, "st", dummy, raising=True)
    monkeypatch.setattr(landing, "_render_logo", lambda: None, raising=True)
    monkeypatch.setattr(
        landing,
        "get_ui_workspace_layout",
        lambda *_args, **_kwargs: SimpleNamespace(base_dir=base),
        raising=True,
    )

    # Stub provisioning e context
    monkeypatch.setattr(landing, "ensure_local_workspace_for_ui", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(landing, "ClientContext", type("_C", (), {"load": staticmethod(lambda **k: _DummyCtx(base))}))
    monkeypatch.setattr(landing, "get_client_context", lambda *_args, **_kwargs: _DummyCtx(base), raising=True)

    def _fake_provision(ctx, log, *, slug, pdf_path, model):
        return {"yaml_paths": {"mapping": str(mapping), "cartelle_raw": str(cartelle)}}

    monkeypatch.setattr(landing.vision_services, "provision_from_vision_with_config", _fake_provision, raising=True)

    # Esegue il rendering
    try:
        landing.render_landing_slug()
    except Exception:
        pass

    # Verifica che sia stato mostrato un box con i path assoluti
    found = False
    for data in dummy.json_calls:
        if str(mapping) == data.get("mapping") and str(cartelle) == data.get("cartelle_raw"):
            found = True
            break
    assert found, "Box percorsi mancanti dopo provisioning"
