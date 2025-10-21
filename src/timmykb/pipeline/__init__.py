"""
Alias di compatibilità per il package `pipeline`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.pipeline")
sys.modules[__name__] = _module
