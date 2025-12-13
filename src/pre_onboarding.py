# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Shim per mantenere compatibilità con `src/pre_onboarding.py`."""

from timmy_kb.cli.pre_onboarding import (
    WorkspaceLayout,
    _create_local_structure,
    _drive_phase,
    _prepare_context_and_logger,
    _require_drive_utils,
    bootstrap_client_workspace,
    ensure_local_workspace_for_ui,
    main,
)

__all__ = [
    "main",
    "_create_local_structure",
    "_drive_phase",
    "_prepare_context_and_logger",
    "_require_drive_utils",
    "bootstrap_client_workspace",
    "WorkspaceLayout",
    "ensure_local_workspace_for_ui",
]


if __name__ == "__main__":
    main()
