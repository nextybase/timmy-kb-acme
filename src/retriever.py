# SPDX-License-Identifier: GPL-3.0-only
"""Shim compatibile per `src.retriever` che punta al nuovo namespace CLI."""

from __future__ import annotations

import sys

from timmy_kb.cli import retriever as _impl

sys.modules[__name__] = _impl
