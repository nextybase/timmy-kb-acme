"""
Alias di compatibilità per il package `ai`.
Permette `import timmykb.ai` mantenendo lo stesso oggetto modulo.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.ai")
sys.modules[__name__] = _module
