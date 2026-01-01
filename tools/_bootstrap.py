# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pipeline.paths import get_repo_root


def bootstrap_repo_src():
    """
    ENTRYPOINT BOOTSTRAP — consentito.

    Determina la repo root per l'entrypoint.
    """
    repo_root = get_repo_root()
    return repo_root


__all__ = ["bootstrap_repo_src"]
