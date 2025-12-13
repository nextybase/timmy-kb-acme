# SPDX-License-Identifier: GPL-3.0-only
"""Shim che espone il modulo `timmy_kb.cli.tag_onboarding_raw` sotto il namespace legacy."""

from __future__ import annotations

import sys

from timmy_kb.cli import tag_onboarding_raw as _impl

sys.modules[__name__] = _impl
