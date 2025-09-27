from __future__ import annotations

from pathlib import Path


def test_single_form_saves_both_yaml(monkeypatch, tmp_path: Path):
    import src.ui.landing_slug as landing

    base = tmp_path / "output" / "timmy-kb-acme"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    (base / "config").mkdir(parents=True, exist_ok=True)

    mapping = sem / "semantic_mapping.yaml"
    cartelle = sem / "cartelle_raw.yaml"
    mapping.write_text("context:\n  slug: old\n", encoding="utf-8")
    cartelle.write_text("version: 1\nfolders: []\n", encoding="utf-8")

    class _DummyCtx:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

    class _DummySt:
        def __init__(self):
            self.session_state = {
                "vision_workflow": {
                    "slug": "acme",
                    "client_name": "",
                    "verified": True,
                    "needs_creation": False,
                    "pdf_bytes": None,
                    "pdf_filename": None,
                    "workspace_created": True,
                    "base_dir": str(base),
                    "yaml_paths": {"mapping": str(mapping), "cartelle_raw": str(cartelle)},
                    "mapping_yaml": mapping.read_text(encoding="utf-8"),
                    "cartelle_yaml": cartelle.read_text(encoding="utf-8"),
                }
            }
            self._text_area_returns = [
                "context:\n  slug: NEW\n",  # mapping
                "version: 1\nfolders:\n  - name: a\n",  # cartelle
            ]
            self._ta_idx = 0

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
            return "acme"

        def button(self, *a, **k):
            return False

        def file_uploader(self, *a, **k):
            return None

        def text_area(self, *a, **k):
            val = self._text_area_returns[self._ta_idx]
            self._ta_idx += 1
            return val

        def form(self, *a, **k):
            class _Form:
                def __enter__(self_inner):
                    return self

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Form()

        def form_submit_button(self, label):
            return label == "Valida & Salva"

        def caption(self, *a, **k):
            return None

        def success(self, *a, **k):
            return None

        def info(self, *a, **k):
            return None

    dummy = _DummySt()
    monkeypatch.setattr(landing, "st", dummy, raising=True)
    monkeypatch.setattr(landing, "_render_logo", lambda: None, raising=True)
    # Evita guardie di path-safety non necessarie nel test
    monkeypatch.setattr(landing, "ensure_within_and_resolve", lambda base, p: p, raising=True)
    monkeypatch.setattr(landing, "ClientContext", type("_C", (), {"load": staticmethod(lambda **k: _DummyCtx(base))}))

    # Esegue: deve arrivare alla sezione editor e salvare entrambi i file
    landing.render_landing_slug()

    assert "NEW" in mapping.read_text(encoding="utf-8")
    assert "folders:" in cartelle.read_text(encoding="utf-8")
