"""
Alias di compatibilità per il package `storage`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.storage")
sys.modules[__name__] = _module
