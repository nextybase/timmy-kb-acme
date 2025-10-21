"""
Alias di compatibilità per il modulo `tag_onboarding`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.tag_onboarding")
sys.modules[__name__] = _module
