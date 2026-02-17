# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Optional

from pipeline.config_utils import get_client_config
from pipeline.env_utils import get_env_var
from pipeline.workspace_bootstrap_service import ensure_local_workspace_for_ui as _ensure_local_workspace_for_ui


def bootstrap_workspace_for_ui(
    slug: str,
    client_name: str,
    *,
    vision_statement_pdf: Optional[bytes] = None,
) -> None:
    """Public runtime boundary for UI workspace bootstrap.

    This keeps UI code decoupled from CLI module paths while preserving
    the current bootstrap behavior.
    """
    _ensure_local_workspace_for_ui(
        slug,
        client_name,
        vision_statement_pdf,
        prompt=lambda _: "",
        get_env_var_fn=get_env_var,
        get_client_config_fn=get_client_config,
    )
