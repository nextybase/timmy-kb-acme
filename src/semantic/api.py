from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Set, TYPE_CHECKING

# Import orchestrator internals (private helpers) and stable public names
from semantic_onboarding import (
    get_paths as _get_paths,
    _convert_raw_to_book as _convert_raw_to_book,
    _enrich_frontmatter as _enrich_frontmatter,
    _write_summary_and_readme as _write_summary_and_readme,
)
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab

# Tipi: a compile-time usiamo il tipo concreto per matchare le firme interne,
# a runtime restiamo decoupled con il Protocol strutturale.
if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType  # type: ignore
else:
    from semantic.types import ClientContextProtocol as ClientContextType  # type: ignore

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
]


def get_paths(slug: str) -> Dict[str, Path]:
    """Wrapper pubblico: risolve i percorsi base/raw/book/semantic per uno slug cliente."""
    return _get_paths(slug)


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    """Wrapper pubblico: carica il vocabolario canonico da SQLite (SSoT).

    Note:
    - La fonte canonica è il DB SQLite sotto `semantic/` (es. `tags.db`).
    - Lo YAML legacy (`tags_reviewed.yaml`) può esistere per migrazione/authoring,
      ma a runtime si legge dal DB per coerenza e tracciabilità.
    """
    return _load_reviewed_vocab(base_dir, logger)


def convert_markdown(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> List[Path]:
    """Wrapper pubblico: converte i PDF in raw/ in Markdown sotto book/."""
    return _convert_raw_to_book(context, logger, slug=slug)


def enrich_frontmatter(
    context: ClientContextType,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
) -> List[Path]:
    """Wrapper pubblico: arricchisce i frontmatter dei Markdown con title e tag canonici."""
    return _enrich_frontmatter(context, logger, vocab, slug=slug)


def write_summary_and_readme(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> None:
    """Wrapper pubblico: garantisce la generazione/validazione di SUMMARY.md e README.md sotto book/."""
    return _write_summary_and_readme(context, logger, slug=slug)
