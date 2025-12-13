# SPDX-License-Identifier: GPL-3.0-only
"""Shim compatibile per mantenere `src.kg_build` importabile."""

from __future__ import annotations

import sys

from timmy_kb.cli import kg_build as _impl

sys.modules[__name__] = _impl
