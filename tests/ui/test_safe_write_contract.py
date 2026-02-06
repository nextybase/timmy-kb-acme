# SPDX-License-Identifier: GPL-3.0-or-later
# tests/ui/test_safe_write_contract.py
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _sig_tuple(fn):
    """Riduci la signature a (kind, name, has_default) per confronto stabile."""
    import inspect

    sig = inspect.signature(fn)
    out = []
    for p in sig.parameters.values():
        has_default = p.default is not inspect._empty
        out.append((p.kind, p.name, has_default))
    return tuple(out)


def test_safe_write_text_signature_matches_backend():
    ui = importlib.import_module("src.ui.utils.core")
    be = importlib.import_module("pipeline.file_utils")
    assert _sig_tuple(ui.safe_write_text) == _sig_tuple(be.safe_write_text)


@pytest.mark.unit
def test_safe_write_text_passes_kwargs(monkeypatch, tmp_path: Path):
    ui = importlib.import_module("src.ui.utils.core")

    called = {}

    def fake_backend(path: Path, data: str, *, encoding="utf-8", atomic=True, fsync=False):
        called["path"] = path
        called["data"] = data
        called["encoding"] = encoding
        called["atomic"] = atomic
        called["fsync"] = fsync

    monkeypatch.setattr(ui, "_safe_write_text", fake_backend, raising=True)

    ui.safe_write_text(tmp_path / "x.txt", "ciao", encoding="utf-8", atomic=True, fsync=True)

    assert called["path"].name == "x.txt"
    assert called["data"] == "ciao"
    assert called["encoding"] == "utf-8"
    assert called["atomic"] is True
    assert called["fsync"] is True
