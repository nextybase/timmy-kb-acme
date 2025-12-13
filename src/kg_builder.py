# SPDX-License-Identifier: GPL-3.0-only
"""Shim compatibile per `src.kg_builder` che punta al namespace CLI."""

from __future__ import annotations

import sys

from timmy_kb.cli import kg_builder as _impl

sys.modules[__name__] = _impl
