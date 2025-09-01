from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Set, TYPE_CHECKING, Protocol, runtime_checkable

# Import orchestrator internals (private helpers) and stable public names
from semantic_onboarding import (
    get_paths as _get_paths,
    _load_reviewed_vocab as _load_reviewed_vocab,
    _convert_raw_to_book as _convert_raw_to_book,
    _enrich_frontmatter as _enrich_frontmatter,
    _write_summary_and_readme as _write_summary_and_readme,
)


# ---- Typing: ClientContext as a Protocol to avoid runtime hard deps while keeping strong typing ----
@runtime_checkable
class ClientContextProtocol(Protocol):
    """Minimal structural contract expected by the façade/orchestrators.

    Add here only the attributes that are *actually* used by downstream calls.
    Keeping it small avoids tight coupling while preserving type-safety.
    """

    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str  # commonly accessed by generators/metadata


if TYPE_CHECKING:  # during type checking, import the real type
    from pipeline.context import ClientContext as ClientContextType  # type: ignore
else:  # at runtime, use the structural Protocol (no Any fallback)
    ClientContextType = ClientContextProtocol  # type: ignore


__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
]


def get_paths(slug: str) -> Dict[str, Path]:
    """Public wrapper: resolve base/raw/book/semantic paths for a client slug."""
    return _get_paths(slug)


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    """Public wrapper: load canonical vocab from SQLite (SSoT).

    Notes:
    - Canonical source is the SQLite DB under `semantic/` (e.g., `tags.db`).
    - Legacy YAML (`tags_reviewed.yaml`) may still exist and be used for migration,
      but runtime reads the canonical vocab from the DB for consistency and auditability.
    """
    return _load_reviewed_vocab(base_dir, logger)


def convert_markdown(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> List[Path]:
    """Public wrapper: convert PDFs under raw/ to Markdown under book/."""
    return _convert_raw_to_book(context, logger, slug=slug)


def enrich_frontmatter(
    context: ClientContextType,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
) -> List[Path]:
    """Public wrapper: enrich Markdown frontmatter with title and canonical tags."""
    return _enrich_frontmatter(context, logger, vocab, slug=slug)


def write_summary_and_readme(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> None:
    """Public wrapper: ensure SUMMARY.md and README.md are generated/validated under book/."""
    return _write_summary_and_readme(context, logger, slug=slug)
