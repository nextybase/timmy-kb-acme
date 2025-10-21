"""
Alias di compatibilità per il package `tools`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.tools")
sys.modules[__name__] = _module
