"""
Alias di compatibilità per il modulo `semantic_headless`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.semantic_headless")
sys.modules[__name__] = _module
