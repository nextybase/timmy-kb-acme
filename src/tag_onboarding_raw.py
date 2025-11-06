# SPDX-License-Identifier: GPL-3.0-only
"""Servizi di acquisizione RAW per l'orchestratore tag_onboarding."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pipeline.config_utils import get_client_config
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import mask_partial, phase_scope, tail_path
from pipeline.path_utils import iter_safe_pdfs
from semantic.api import copy_local_pdfs_to_raw
from semantic.types import ClientContextProtocol

try:
    from pipeline.drive_utils import download_drive_pdfs_to_local, get_drive_service
except Exception:  # pragma: no cover
    download_drive_pdfs_to_local = None
    get_drive_service = None


def _require_drive_utils() -> None:
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(download_drive_pdfs_to_local):
        missing.append("download_drive_pdfs_to_local")
    if missing:
        raise ConfigError(
            "Sorgente Drive selezionata ma dipendenze non installate. "
            f"Funzioni mancanti: {', '.join(missing)}.\n"
            "Installa gli extra: pip install .[drive]",
        )


def download_from_drive(
    context: ClientContextProtocol,
    logger: logging.Logger,
    *,
    raw_dir: Path,
    non_interactive: bool,
) -> None:
    """Scarica i PDF da Drive nella cartella RAW usando le stesse guardie dell'orchestratore."""
    cfg = get_client_config(context) or {}
    drive_raw_folder_id = cfg.get("drive_raw_folder_id")
    if not drive_raw_folder_id:
        raise ConfigError("drive_raw_folder_id mancante in config.yaml.")

    _require_drive_utils()
    service = get_drive_service(context)

    with phase_scope(logger, stage="drive_download", customer=context.slug) as phase:
        download_drive_pdfs_to_local(  # type: ignore[call-arg]
            service=service,
            remote_root_folder_id=drive_raw_folder_id,
            local_root_dir=raw_dir,
            progress=not non_interactive,
            context=context,
            redact_logs=getattr(context, "redact_logs", False),
        )
        try:
            pdfs = list(iter_safe_pdfs(raw_dir))
            phase.set_artifacts(len(pdfs))
        except Exception:
            phase.set_artifacts(None)

    logger.info(
        "cli.tag_onboarding.drive_download_completed",
        extra={"folder_id": mask_partial(drive_raw_folder_id)},
    )


def copy_from_local(
    logger: logging.Logger,
    *,
    raw_dir: Path,
    local_path: Optional[str],
    non_interactive: bool,
    context: ClientContextProtocol,
) -> None:
    """Copia i PDF da una sorgente locale in raw/ evitando duplicazioni."""
    if not local_path:
        local_path = str(raw_dir)
        logger.info(
            "Nessun --local-path fornito: uso RAW del cliente come sorgente",
            extra={"raw": str(raw_dir), "slug": context.slug},
        )

    src_dir = Path(local_path).expanduser().resolve()
    if src_dir == raw_dir.expanduser().resolve():
        logger.info(
            "cli.tag_onboarding.source_matches_raw",
            extra={"raw": str(raw_dir)},
        )
        return

    with phase_scope(logger, stage="local_copy", customer=context.slug) as phase:
        copied = copy_local_pdfs_to_raw(src_dir, raw_dir, logger)
        try:
            phase.set_artifacts(int(copied))
        except Exception:
            phase.set_artifacts(None)

    logger.info(
        "cli.tag_onboarding.local_copy_completed",
        extra={"count": copied, "raw_tail": tail_path(raw_dir)},
    )


__all__ = ["download_from_drive", "copy_from_local"]
