# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Shim che re-esporta `tag_onboarding_semantic` dal namespace timmy_kb.cli."""

from timmy_kb.cli.tag_onboarding_semantic import emit_csv_phase, emit_stub_phase

__all__ = ["emit_csv_phase", "emit_stub_phase"]
