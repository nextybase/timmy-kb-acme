# SPDX-License-Identifier: GPL-3.0-or-later
"""Wrapper per le integrazioni Drive opzionali usate dalla dummy KB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional


class _Ctx:
    """Contesto minimo compatibile con runner Drive (serve .base_dir)."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


def call_drive_min(
    slug: str,
    client_name: str,
    base_dir: Path,
    logger: logging.Logger,
    ensure_drive_minimal_and_upload_config: Callable[..., Any] | None,
) -> Optional[dict[str, Any]]:
    """Chiama ensure_drive_minimal_and_upload_config con firme UI. Skip silenzioso se non disponibile."""
    if not callable(ensure_drive_minimal_and_upload_config):
        return None
    ctx = _Ctx(base_dir)
    try:
        # firma principale (ctx, slug, client_folder_id=None, logger=None)
        return ensure_drive_minimal_and_upload_config(ctx, slug=slug, client_folder_id=None, logger=logger)  # type: ignore[arg-type]
    except TypeError:
        # fallback legacy: (slug, client_name)
        return ensure_drive_minimal_and_upload_config(slug=slug, client_name=client_name)  # type: ignore[misc]


def call_drive_build_from_mapping(
    slug: str,
    client_name: str,
    base_dir: Path,
    logger: logging.Logger,
    build_drive_from_mapping: Callable[..., Any] | None,
) -> Optional[dict[str, Any]]:
    """Chiama build_drive_from_mapping come fa la UI (se disponibile)."""
    if not callable(build_drive_from_mapping):
        return None
    return build_drive_from_mapping(slug=slug, client_name=client_name)  # type: ignore[misc]


def call_drive_emit_readmes(
    slug: str,
    base_dir: Path,
    logger: logging.Logger,
    emit_readmes_for_raw: Callable[..., Any] | None,
) -> Optional[dict[str, Any]]:
    """Upload dei README delle cartelle RAW su Drive (best-effort)."""
    if not callable(emit_readmes_for_raw):
        return None
    try:
        base_root = base_dir.parent
        return emit_readmes_for_raw(  # type: ignore[misc]
            slug,
            base_root=base_root,
            require_env=False,
            ensure_structure=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tools.gen_dummy_kb.drive_readmes_failed",
            extra={"slug": slug, "error": str(exc)},
        )
        return None


__all__ = ["call_drive_min", "call_drive_build_from_mapping", "call_drive_emit_readmes"]
