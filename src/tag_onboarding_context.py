# SPDX-License-Identifier: GPL-3.0-only
"""Utility di setup contesto per l'orchestratore tag_onboarding."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within


@dataclass(frozen=True)
class ContextResources:
    """Raccoglie gli artefatti principali necessari all'orchestratore."""

    context: ClientContext
    base_dir: Path
    raw_dir: Path
    semantic_dir: Path
    logger: logging.Logger
    log_file: Path


def prepare_context(
    slug: str,
    *,
    non_interactive: bool,
    run_id: Optional[str],
    require_env: bool,
) -> ContextResources:
    """Carica il contesto cliente e restituisce percorsi/log pronti all'uso."""
    context = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=require_env,
        run_id=run_id,
    )

    base_dir = getattr(context, "base_dir", None) or (
        Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
    )
    base_dir = Path(base_dir).resolve()
    ensure_within(base_dir.parent, base_dir)

    raw_dir = getattr(context, "raw_dir", None)
    raw_dir = Path(raw_dir) if raw_dir is not None else base_dir / "raw"
    semantic_dir = getattr(context, "semantic_dir", None)
    semantic_dir = Path(semantic_dir) if semantic_dir is not None else base_dir / "semantic"

    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)

    log_file = base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    ensure_within(base_dir, log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger("tag_onboarding", log_file=log_file, context=context, run_id=run_id)

    return ContextResources(
        context=context,
        base_dir=base_dir,
        raw_dir=raw_dir,
        semantic_dir=semantic_dir,
        logger=logger,
        log_file=log_file,
    )


__all__ = ["ContextResources", "prepare_context"]
