# SPDX-License-Identifier: GPL-3.0-only
"""Fasi semantiche (CSV e stub) dell'orchestratore tag_onboarding."""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline.logging_utils import phase_scope, tail_path
from pipeline.path_utils import open_for_read_bytes_selfguard
from semantic.api import build_tags_csv
from semantic.tags_io import write_tagging_readme, write_tags_review_stub_from_csv
from semantic.types import ClientContextProtocol


def emit_csv_phase(
    context: ClientContextProtocol,
    logger: logging.Logger,
    *,
    slug: str,
    raw_dir: Path,
    semantic_dir: Path,
) -> Path:
    """Genera il CSV dei tag grezzi e restituisce il percorso al file prodotto."""
    with phase_scope(logger, stage="emit_csv", customer=context.slug) as phase:
        csv_path: Path = build_tags_csv(context, logger, slug=slug)
        try:
            line_count = 0
            with open_for_read_bytes_selfguard(csv_path) as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    line_count += chunk.count(b"\n")
            phase.set_artifacts(max(0, line_count - 1))
        except Exception:
            phase.set_artifacts(None)

    logger.info(
        "cli.tag_onboarding.csv_emitted",
        extra={"file_path": str(csv_path), "file_path_tail": tail_path(csv_path)},
    )
    return csv_path


def emit_stub_phase(
    semantic_dir: Path,
    csv_path: Path,
    logger: logging.Logger,
    *,
    context: ClientContextProtocol,
) -> None:
    """Crea README/tag stub nella cartella semantic/ a partire dal CSV approvato."""
    with phase_scope(logger, stage="semantic_stub", customer=context.slug) as phase:
        write_tagging_readme(semantic_dir, logger)
        write_tags_review_stub_from_csv(semantic_dir, csv_path, logger)
        try:
            phase.set_artifacts(2)
        except Exception:
            phase.set_artifacts(None)

    logger.info(
        "Arricchimento semantico completato",
        extra={"semantic_dir": str(semantic_dir), "semantic_tail": tail_path(semantic_dir)},
    )


__all__ = ["emit_csv_phase", "emit_stub_phase"]
