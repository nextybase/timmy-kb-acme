# SPDX-License-Identifier: GPL-3.0-only
"""
Alias di compatibilità per il modulo `retriever`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.retriever")
sys.modules[__name__] = _module
