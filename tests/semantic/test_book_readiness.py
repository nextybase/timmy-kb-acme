# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import builtins
import importlib
import logging
import sys


def test_constants_import_failure_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="semantic.book_readiness")
    module_name = "semantic.book_readiness"

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "semantic.constants":
            raise ImportError("test fallback")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        if module_name in sys.modules:
            del sys.modules[module_name]
        importlib.import_module(module_name)
    finally:
        monkeypatch.setattr(builtins, "__import__", original_import)

    record = [
        entry
        for entry in caplog.records
        if entry.name == "semantic.book_readiness" and entry.event == "semantic.book_readiness.constants_fallback"
    ]
    assert record
