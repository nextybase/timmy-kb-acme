# tests/ui/test_safe_write_text_passthrough.py
from __future__ import annotations

import importlib
from pathlib import Path


def test_safe_write_text_passes_fsync(monkeypatch, tmp_path):
    ui = importlib.import_module("src.ui.utils.core")

    called = {}

    def fake_backend(path: Path, data: str, *, encoding="utf-8", atomic=True, fsync=False):
        called["path"] = path
        called["data"] = data
        called["encoding"] = encoding
        called["atomic"] = atomic
        called["fsync"] = fsync

    # Patchiamo la reference usata dal wrapper UI
    monkeypatch.setattr(ui, "_safe_write_text", fake_backend, raising=True)

    ui.safe_write_text(tmp_path / "x.txt", "ciao", encoding="utf-8", atomic=True, fsync=True)

    assert called["path"].name == "x.txt"
    assert called["data"] == "ciao"
    assert called["encoding"] == "utf-8"
    assert called["atomic"] is True
    assert called["fsync"] is True
