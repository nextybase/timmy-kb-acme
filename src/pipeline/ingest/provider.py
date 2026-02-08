# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol

from pipeline.beta_flags import is_beta_strict
from pipeline.config_utils import get_client_config, get_drive_id
from pipeline.context import ClientContext
from pipeline.exceptions import CapabilityUnavailableError, ConfigError
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within, iter_safe_pdfs
from semantic.api import copy_local_pdfs_to_raw

try:
    from pipeline.drive_utils import download_drive_pdfs_to_local, get_drive_service
except ImportError:  # pragma: no cover
    download_drive_pdfs_to_local = None
    get_drive_service = None


class IngestProvider(Protocol):
    def ingest_raw(
        self,
        *,
        context: ClientContext,
        raw_dir: Path,
        logger: logging.Logger,
        non_interactive: bool,
        local_path: Optional[Path] = None,
    ) -> int | None: ...


class DriveIngestProvider:
    def ingest_raw(
        self,
        *,
        context: ClientContext,
        raw_dir: Path,
        logger: logging.Logger,
        non_interactive: bool,
        local_path: Optional[Path] = None,
    ) -> int | None:
        cfg = get_client_config(context) or {}
        raw_folder_id = get_drive_id(cfg, "raw_folder_id")
        if not raw_folder_id:
            raise ConfigError("integrations.drive.raw_folder_id mancante in config.yaml.")

        if not callable(get_drive_service) or not callable(download_drive_pdfs_to_local):
            raise CapabilityUnavailableError(
                "Drive capability not available. Install extra dependencies with: pip install .[drive]"
            )

        service = get_drive_service(context)

        strict_mode = is_beta_strict()
        pdf_count: int | None = None
        with phase_scope(logger, stage="drive_download", customer=getattr(context, "slug", None)) as phase:
            download_drive_pdfs_to_local(
                service=service,
                remote_root_folder_id=raw_folder_id,
                local_root_dir=raw_dir,
                progress=not non_interactive,
                context=context,
                redact_logs=getattr(context, "redact_logs", False),
            )
            try:
                pdfs = list(iter_safe_pdfs(raw_dir))
                pdf_count = len(pdfs)
                phase.set_artifacts(pdf_count)
            except Exception as exc:
                phase.set_artifacts(None)
                _handle_drive_count_failure(logger, context, strict_mode, exc)

        logger.info(
            "ingest_provider.drive_completed",
            extra={"folder_id": raw_folder_id, "slug": getattr(context, "slug", None)},
        )

        return pdf_count


def _handle_drive_count_failure(
    logger: logging.Logger,
    context: ClientContext,
    strict_mode: bool,
    exc: Exception,
) -> None:
    extra = {
        "slug": getattr(context, "slug", None),
        "service_only": True,
        "stage": "drive_count",
    }
    logger.warning("ingest_provider.drive_count_failed", extra=extra)
    if strict_mode:
        raise ConfigError(
            "Drive PDF count failed; strict mode requires deterministic artifacts.",
            slug=getattr(context, "slug", None),
        ) from exc


class LocalIngestProvider:
    def ingest_raw(
        self,
        *,
        context: ClientContext,
        raw_dir: Path,
        logger: logging.Logger,
        non_interactive: bool,
        local_path: Optional[Path] = None,
    ) -> int | None:
        raw_dir = raw_dir.resolve()
        ensure_within(raw_dir.parent, raw_dir)
        if local_path is None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "ingest_provider.local.noop",
                extra={"raw": str(raw_dir), "slug": getattr(context, "slug", None)},
            )
            return 0

        src_path = local_path.resolve()
        if src_path == raw_dir:
            logger.info(
                "ingest_provider.local.same_path",
                extra={"raw": str(raw_dir), "slug": getattr(context, "slug", None)},
            )
            return 0

        with phase_scope(logger, stage="local_copy", customer=getattr(context, "slug", None)) as phase:
            copied: int = copy_local_pdfs_to_raw(src_path, raw_dir, logger)
            try:
                phase.set_artifacts(int(copied))
            except Exception:
                phase.set_artifacts(None)

        logger.info(
            "ingest_provider.local_completed",
            extra={"count": copied, "slug": getattr(context, "slug", None)},
        )

        return copied


def build_ingest_provider(source: str) -> IngestProvider:
    source_key = source.lower()
    if source_key == "drive":
        return DriveIngestProvider()
    if source_key == "local":
        return LocalIngestProvider()
    raise ConfigError(f"Source non supportata: {source}. Usa 'drive' o 'local'.")
