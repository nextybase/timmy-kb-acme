# SPDX-License-Identifier: GPL-3.0-only
"""
Alias di compatibilità per il modulo `ingest`.
"""

from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("src.ingest")
sys.modules[__name__] = _module
