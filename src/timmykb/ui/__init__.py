# SPDX-License-Identifier: GPL-3.0-only
"""
Alias di compatibilità per il package `ui`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.ui")
sys.modules[__name__] = _module
