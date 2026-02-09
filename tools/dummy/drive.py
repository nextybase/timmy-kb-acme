# tools/dummy/drive.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""DUMMY / SMOKE SUPER-TEST ONLY
FORBIDDEN IN RUNTIME-CORE (src/)
Fallback behavior is intentional and confined to this perimeter

Wrapper per le integrazioni Drive opzionali usate dalla dummy KB.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.workspace_layout import WorkspaceLayout


class _LayoutCtx:
    """
    Contesto minimale layout-first compatibile con runner Drive.
    Espone solo repo_root_dir e deriva i path via WorkspaceLayout.
    """

    def __init__(self, *, slug: str, repo_root_dir: Path) -> None:
        self.slug = slug
        self.repo_root_dir = repo_root_dir
        self._layout = WorkspaceLayout.from_context(self)

    @property
    def base_dir(self) -> Path:
        return self._layout.base_dir

    @property
    def raw_dir(self) -> Path:
        return self._layout.raw_dir

    @property
    def book_dir(self) -> Path:
        return self._layout.book_dir


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
    ctx = _LayoutCtx(slug=slug, repo_root_dir=base_dir)
    try:
        # firma principale (ctx, slug, client_folder_id=None, logger=None)
        return ensure_drive_minimal_and_upload_config(  # type: ignore[arg-type]
            ctx, slug=slug, client_folder_id=None, logger=logger
        )
    except TypeError as exc:
        # Dummy = smoke e2e: una firma sbagliata è regressione, non compat fallback.
        raise RuntimeError(
            "Firma non compatibile per ensure_drive_minimal_and_upload_config (attesa: (ctx, *, slug, client_folder_id, logger))."
        ) from exc


def call_drive_emit_readmes(
    slug: str,
    base_dir: Path,
    logger: logging.Logger,
    emit_readmes_for_raw: Callable[..., Any] | None,
    *,
    deep_testing: bool = False,
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
        )
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        normalized = message.casefold()
        if any(
            signal in normalized
            for signal in (
                "cartella 'raw' non trovata",
                "drive_id non impostato",
                "funzionalita google drive non disponibili",
                "installa gli extra",
            )
        ):
            logger.info(
                "tools.gen_dummy_kb.drive_readmes_skipped",
                extra={"slug": slug, "error": message},
            )
        else:
            logger.exception(
                "tools.gen_dummy_kb.drive_readmes_failed",
                extra={"slug": slug, "error": message},
            )
            if deep_testing:
                raise
        return None


__all__ = ["call_drive_min", "call_drive_emit_readmes"]
