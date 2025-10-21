"""
Alias di compatibilità per il modulo `prompt_builder`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.prompt_builder")
sys.modules[__name__] = _module
