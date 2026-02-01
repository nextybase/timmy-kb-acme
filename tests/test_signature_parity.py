# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_signature_parity.py
from __future__ import annotations

import importlib
import inspect


def _sig_tuple(fn):
    """Riduci la signature a (kind, name, has_default) per confronto stabile tra UI e backend."""
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
