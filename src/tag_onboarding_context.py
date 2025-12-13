# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Shim che re-esporta `tag_onboarding_context` dal namespace `timmy_kb.cli`."""

from timmy_kb.cli.tag_onboarding_context import ContextResources, prepare_context

__all__ = ["ContextResources", "prepare_context"]
