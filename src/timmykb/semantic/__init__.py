"""
Alias di compatibilità per il package `semantic`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.semantic")
sys.modules[__name__] = _module
