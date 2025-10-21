"""
Alias di compatibilità per il modulo `vscode_bridge`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.vscode_bridge")
sys.modules[__name__] = _module
