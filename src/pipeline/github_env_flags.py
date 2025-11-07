# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper per la gestione dei flag/variabili ambiente nel push GitHub."""

from __future__ import annotations

import os
from fnmatch import fnmatch
from typing import Any, Iterable

from pipeline.env_utils import get_env_var

from .github_types import SupportsContext

__all__ = [
    "get_force_allowed_branches",
    "is_branch_allowed_for_force",
    "should_push",
]


def _iter_patterns(raw: Any) -> Iterable[str]:
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple, set, frozenset)):
        iterable = raw
    else:
        iterable = str(raw).split(",")
    return (str(entry).strip() for entry in iterable if str(entry).strip())


def get_force_allowed_branches(context: SupportsContext) -> list[str]:
    env_map = getattr(context, "env", {}) or {}
    raw = env_map.get("GIT_FORCE_ALLOWED_BRANCHES")
    if raw is None:
        raw = os.environ.get("GIT_FORCE_ALLOWED_BRANCHES")
    return list(_iter_patterns(raw))


def is_branch_allowed_for_force(branch: str, context: SupportsContext, *, allow_if_unset: bool = True) -> bool:
    patterns = get_force_allowed_branches(context)
    if not patterns:
        return bool(allow_if_unset)

    branch_value = str(branch or "").strip()
    return any(fnmatch(branch_value, pattern) for pattern in patterns)


def should_push(context: SupportsContext) -> bool:
    """Determina se eseguire il push su GitHub in base ai flag di contesto/env."""
    env_map = getattr(context, "env", {}) or {}
    if str(env_map.get("TIMMY_NO_GITHUB", "")).lower() in {"true", "1", "yes"}:
        return False

    skip_push = get_env_var("SKIP_GITHUB_PUSH", default=None)
    if skip_push is not None and str(skip_push).strip().lower() not in {"", "0", "false"}:
        return False

    return True
