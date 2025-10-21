"""
Alias di compatibilità per il modulo `onboarding_full`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.onboarding_full")
sys.modules[__name__] = _module
