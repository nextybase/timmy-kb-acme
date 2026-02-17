# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Optional, cast

from pipeline.drive_bootstrap_service import create_local_structure, drive_phase, prepare_context_and_logger


def ensure_drive_minimal_and_upload_config(slug: str, client_name: Optional[str] = None) -> Path:
    """Public runtime boundary for minimal Drive bootstrap + config upload."""
    ctx, logger, resolved_name = prepare_context_and_logger(
        slug,
        interactive=False,
        require_drive_env=False,
        run_id=None,
        client_name=client_name,
        prompt=lambda _: "",
    )
    cfg_path = cast(Path, create_local_structure(ctx, logger, client_name=(resolved_name or slug)))
    drive_phase(
        ctx,
        logger,
        config_path=cfg_path,
        client_name=(resolved_name or slug),
        require_env=True,
    )
    return cfg_path
