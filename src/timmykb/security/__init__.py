"""
Alias di compatibilità per il package `security`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.security")
sys.modules[__name__] = _module
