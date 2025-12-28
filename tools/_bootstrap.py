# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pipeline.paths import ensure_src_on_sys_path, get_repo_root


def bootstrap_repo_src():
    """
    ENTRYPOINT BOOTSTRAP — consentito.

    Determina la repo root e garantisce che <repo>/src sia in sys.path
    tramite la SSoT pipeline.paths (nessuna logica duplicata).
    """
    repo_root = get_repo_root()
    ensure_src_on_sys_path(repo_root)
    return repo_root


__all__ = ["bootstrap_repo_src"]
