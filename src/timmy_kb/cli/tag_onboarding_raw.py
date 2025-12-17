# SPDX-License-Identifier: GPL-3.0-only
"""Servizi di acquisizione RAW per l'orchestratore tag_onboarding."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pipeline.config_utils import get_client_config
from pipeline.drive_utils import download_drive_pdfs_to_local, get_drive_service
from pipeline.ingest.provider import build_ingest_provider
from pipeline.logging_utils import get_structured_logger
from semantic.api import copy_local_pdfs_to_raw
from semantic.types import ClientContextProtocol


def _normalize_provider(cfg: dict[str, str | bool], source: str) -> str:
    provider = cfg.get("ingest_provider")
    if provider in {"drive", "local"}:
        return provider
    if source in {"drive", "local"}:
        return source
    skip_drive = bool(cfg.get("skip_drive"))
    return "local" if skip_drive else "drive"


def _resolve_provider(
    context: ClientContextProtocol,
    logger: logging.Logger,
    *,
    source: str,
):
    try:
        cfg = get_client_config(context) or {}
    except AttributeError:
        cfg = {}
    provider_key = _normalize_provider(cfg, source)
    logger_extra = getattr(logger, "extra", None)
    ingest_logger = get_structured_logger("tag_onboarding.ingest", **dict(logger_extra or {}))
    return build_ingest_provider(provider_key), provider_key, ingest_logger


def download_from_drive(
    context: ClientContextProtocol,
    logger: logging.Logger,
    *,
    raw_dir: Path,
    non_interactive: bool,
) -> int:
    provider, *_ = _resolve_provider(context, logger, source="drive")
    return provider.ingest_raw(
        context=context,
        raw_dir=raw_dir,
        logger=logger,
        non_interactive=non_interactive,
    )


def copy_from_local(
    logger: logging.Logger,
    *,
    raw_dir: Path,
    local_path: Optional[str],
    non_interactive: bool,
    context: ClientContextProtocol,
) -> int:
    provider, *_ = _resolve_provider(context, logger, source="local")
    local_dir = Path(local_path).expanduser().resolve() if local_path else None
    return provider.ingest_raw(
        context=context,
        raw_dir=raw_dir,
        logger=logger,
        non_interactive=non_interactive,
        local_path=local_dir,
    )


__all__ = [
    "copy_local_pdfs_to_raw",
    "download_drive_pdfs_to_local",
    "get_drive_service",
    "download_from_drive",
    "copy_from_local",
]
