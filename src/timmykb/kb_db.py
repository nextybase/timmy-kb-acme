"""
Alias di compatibilità per il modulo `kb_db`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.kb_db")
sys.modules[__name__] = _module
