# SPDX-License-Identifier: GPL-3.0-only
# src/adapters/book_purity.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.path_utils import ensure_within, iter_safe_paths


def _as_path(value: Any) -> Optional[Path]:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    return None


def _is_under_ignored_subdir(book_dir: Path, p: Path) -> bool:
    try:
        rel = p.relative_to(book_dir)
    except ValueError:
        return False
    parts = rel.parts
    return bool(parts) and parts[0].lower() in {"_book", "node_modules", ".cache", ".tmp", ".git"}


def ensure_book_purity(context: Any, logger: logging.Logger) -> None:
    """Garantisce che `book/` contenga solo file consentiti.

    - Consentiti: `*.md` (e placeholder `*.md.fp`).
    - Consentiti builder: `book.json`, `package.json`,
      `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`.
    - Ignorati: `_book/`, `node_modules/`, `.cache/`, `.tmp/`, `.git/`.
    - Consentito speciale: `.DS_Store`.

    Solleva PipelineError con elenco delle violazioni.
    """
    md_dir = _as_path(getattr(context, "md_dir", None))
    base_dir = _as_path(getattr(context, "base_dir", None))
    repo_root = _as_path(getattr(context, "repo_root_dir", None))

    if md_dir is not None:
        book_dir = md_dir
        if base_dir is not None:
            ensure_within(base_dir, book_dir)
    elif base_dir is not None:
        book_dir = base_dir / "book"
        ensure_within(base_dir, book_dir)
    elif repo_root is not None:
        book_dir = repo_root / "book"
        ensure_within(repo_root, book_dir)
    else:
        raise ConfigError("Contesto privo di percorsi utili: servono md_dir o base_dir o repo_root_dir.")

    if not book_dir.exists() or not book_dir.is_dir():
        raise ConfigError(f"Cartella book/ non trovata: {book_dir}")

    allowed_special = {".ds_store"}
    allowed_builder = {
        "book.json",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    }

    bad: list[Path] = []
    for p in iter_safe_paths(book_dir, include_dirs=False, include_files=True):
        if _is_under_ignored_subdir(book_dir, p):
            continue
        name = p.name.lower()
        if name.endswith(".md") or name.endswith(".md.fp"):
            continue
        if name in allowed_special or name in allowed_builder:
            continue
        bad.append(p)

    if bad:
        rels: list[str] = []
        for p in bad:
            try:
                rels.append(p.relative_to(book_dir).as_posix())
            except Exception:
                rels.append(p.name)
        logger.error("book.purity.fail", extra={"count": len(bad)})
        raise PipelineError("File non consentiti in book/: " + ", ".join(sorted(rels)))
    logger.info("book.purity.ok", extra={"book": str(book_dir)})
