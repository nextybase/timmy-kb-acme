# SPDX-License-Identifier: GPL-3.0-or-later
"""Servizi dedicati alla conversione RAW -> Markdown della pipeline semantica."""

from __future__ import annotations

import datetime as _dt
import inspect
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple, cast

from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from pipeline.frontmatter_utils import dump_frontmatter, read_frontmatter
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe
from pipeline.workspace_layout import WorkspaceLayout
from semantic.auto_tagger import extract_semantic_candidates
from semantic.config import load_semantic_config
from semantic.context_paths import ContextPaths, resolve_context_paths
from semantic.embedding_service import list_content_markdown
from semantic.types import ClientContextProtocol

__all__ = ["convert_markdown", "discover_normalized_inputs", "_call_convert_md"]


@dataclass(frozen=True)
class NormalizedDiscovery:
    safe_mds: Tuple[Path, ...]
    discarded_unsafe: int


def convert_markdown(
    context: ClientContextProtocol,
    logger: logging.Logger,
    *,
    slug: str,
) -> List[Path]:
    """Converte i Markdown in normalized/ in Markdown strutturato dentro book/."""
    start_ts = time.perf_counter()
    layout = WorkspaceLayout.from_context(context)  # type: ignore[arg-type]
    paths = resolve_context_paths(layout)
    repo_root_dir, normalized_dir, book_dir = paths.repo_root_dir, paths.normalized_dir, paths.book_dir
    ensure_within(repo_root_dir, normalized_dir)
    ensure_within(repo_root_dir, book_dir)

    book_dir.mkdir(parents=True, exist_ok=True)

    discovery = discover_normalized_inputs(normalized_dir, logger, slug)
    safe_mds = list(discovery.safe_mds)
    discarded_unsafe = discovery.discarded_unsafe

    if discarded_unsafe > 0:
        logger.info("semantic.convert.discarded_unsafe", extra={"slug": slug, "count": discarded_unsafe})

    if discarded_unsafe > 0 and not safe_mds:
        raise ConfigError(
            (
                f"Trovati solo Markdown non sicuri/fuori perimetro in normalized (scartati={discarded_unsafe}). "
                "Rimuovi i symlink o sposta i file reali dentro 'normalized/' e riprova."
            ),
            slug=slug,
            file_path=paths.normalized_dir,
        )

    result = _run_markdown_conversion(
        paths,
        book_dir,
        logger,
        safe_mds=safe_mds,
        discarded_unsafe=discarded_unsafe,
        start_ts=start_ts,
    )

    if not result:
        raise ConfigError(
            "Nessun Markdown valido trovato in normalized/ e nessun contenuto preesistente.",
            slug=slug,
            file_path=paths.normalized_dir,
        )

    return result


def discover_normalized_inputs(normalized_dir: Path, logger: logging.Logger, slug: str) -> NormalizedDiscovery:
    """Valida normalized/ e restituisce i Markdown sicuri con conteggio scarti."""
    if not normalized_dir.exists():
        raise ConfigError(
            f"Cartella normalized locale non trovata: {normalized_dir}",
            slug=slug,
            file_path=normalized_dir,
        )
    if not normalized_dir.is_dir():
        raise ConfigError(
            f"Percorso normalized non e' una directory: {normalized_dir}",
            slug=slug,
            file_path=normalized_dir,
        )

    safe, discarded = _collect_safe_markdown(normalized_dir, logger, slug)
    return NormalizedDiscovery(safe_mds=tuple(safe), discarded_unsafe=discarded)


def _call_convert_md(convert_fn, ctx: ContextPaths, book_dir: Path) -> None:
    if not callable(convert_fn):
        raise ConversionError(
            "convert_md call failed: not callable",
            slug=ctx.slug,
            file_path=book_dir,
        )
    try:
        signature = inspect.signature(convert_fn)
        if "book_dir" in signature.parameters:
            try:
                convert_fn(ctx, book_dir=book_dir)
            except TypeError:
                convert_fn(ctx, book_dir)
        else:
            convert_fn(ctx)
    except TypeError as exc:
        raise ConversionError(
            "convert_md call failed",
            slug=ctx.slug,
            file_path=book_dir,
        ) from exc


def _collect_safe_markdown(normalized_dir: Path, logger: logging.Logger, slug: str) -> Tuple[List[Path], int]:
    """Raccoglie Markdown sicuri sotto normalized_dir rispettando la path-safety della pipeline."""
    from pipeline import path_utils as ppath

    safe: List[Path] = []
    discarded = 0

    def _on_skip(candidate: Path, reason: str) -> None:
        nonlocal discarded
        discarded += 1
        if reason == "symlink":
            logger.warning(
                "semantic.convert.skip_symlink",
                extra={"slug": slug, "file_path": str(candidate)},
            )
        else:
            logger.warning(
                "semantic.convert.skip_unsafe",
                extra={"slug": slug, "file_path": str(candidate), "error": reason},
            )

    # Usiamo sempre la scansione "fresh" per evitare cache stale tra run/test.
    for safe_path in ppath.iter_safe_paths(
        normalized_dir,
        include_dirs=False,
        include_files=True,
        suffixes=(".md",),
        on_skip=_on_skip,
    ):
        safe.append(safe_path)

    return safe, discarded


def _write_markdown_for_normalized(
    md_path: Path,
    normalized_root: Path,
    book_root: Path,
    candidates: dict[str, dict[str, object]],
    *,
    slug: str,
) -> Path:
    rel_md = md_path.relative_to(normalized_root)
    book_candidate = book_root / rel_md
    book_path = cast(Path, ensure_within_and_resolve(book_root, book_candidate))
    book_path.parent.mkdir(parents=True, exist_ok=True)

    rel_from_base = None
    try:
        rel_from_base = md_path.relative_to(normalized_root.parent)
    except Exception:
        rel_from_base = rel_md
    candidate_key = rel_from_base.as_posix()
    candidate_meta = candidates.get(candidate_key, {})
    tags_raw = candidate_meta.get("tags") or []
    tags_sorted = sorted({str(t).strip() for t in tags_raw if str(t).strip()})

    text = read_text_safe(normalized_root, md_path, encoding="utf-8")
    body = text.strip()
    if not body:
        raise ConversionError(
            "Markdown normalizzato vuoto.",
            slug=slug,
            file_path=str(md_path),
        )
    body = body + "\n"

    existing_created_at: str | None = None
    existing_meta: dict[str, object] = {}
    if book_path.exists():
        try:
            existing_meta, body_prev = read_frontmatter(book_root, book_path, use_cache=False, allow_fallback=True)
            existing_created_at = str(existing_meta.get("created_at") or "").strip() or None
            if body_prev.strip() == body.strip() and existing_meta.get("tags_raw") == tags_sorted:
                return book_path
        except Exception:
            existing_created_at = None
            existing_meta = {}

    meta: dict[str, object] = {
        "title": rel_md.stem.replace("_", " ").replace("-", " ").title() or rel_md.stem,
        "source_category": rel_md.parent.as_posix() or None,
        "source_file": rel_md.name,
        "created_at": existing_created_at or _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds"),
        "tags_raw": tags_sorted,
    }
    for key, value in existing_meta.items():
        if key not in meta:
            meta[key] = value
    excerpt = body[:2048].rstrip()
    if excerpt:
        meta["excerpt"] = excerpt if len(excerpt) <= 2048 else excerpt[:2048]

    payload = dump_frontmatter(meta) + body
    safe_write_text(book_path, payload, encoding="utf-8", atomic=True)
    return book_path


def _convert_normalized_markdown(
    paths: ContextPaths,
    book_dir: Path,
    safe_mds: Sequence[Path],
    *,
    logger: logging.Logger,
) -> List[Path]:
    cfg = load_semantic_config(paths.repo_root_dir)
    candidates = extract_semantic_candidates(paths.normalized_dir, cfg)
    written: list[Path] = []
    for md_path in safe_mds:
        written.append(
            _write_markdown_for_normalized(
                md_path,
                paths.normalized_dir,
                book_dir,
                candidates,
                slug=paths.slug,
            )
        )
    return written


def _log_conversion_success(
    logger: logging.Logger,
    slug: str,
    *,
    ms: int,
    content_count: int,
    mode: str,
    reuse_count: int | None = None,
) -> None:
    if mode == "reuse" and reuse_count is not None:
        logger.info(
            "semantic.convert.reused_existing_content",
            extra={"slug": slug, "count": reuse_count},
        )
    logger.info(
        "semantic.convert_markdown.done",
        extra={
            "slug": slug,
            "ms": ms,
            "artifacts": {"content_files": content_count},
        },
    )
    logger.info(
        "semantic.convert.summary",
        extra={
            "slug": slug,
            "mode": mode,
            "content_files": content_count,
        },
    )


def _run_markdown_conversion(
    paths: ContextPaths,
    book_dir: Path,
    logger: logging.Logger,
    *,
    safe_mds: Sequence[Path],
    discarded_unsafe: int,
    start_ts: float,
) -> List[Path]:

    slug = paths.slug
    if safe_mds:
        safe_list = list(safe_mds)
    else:
        safe_list = []

    if not safe_list and not any(book_dir.glob("*.md")):
        logger.info(
            "semantic.convert.no_files",
            extra={"slug": slug, "normalized_dir": str(paths.normalized_dir), "book_dir": str(book_dir)},
        )
        raise ConfigError(
            "Nessun Markdown valido trovato in normalized/ e nessun contenuto preesistente.",
            slug=slug,
            file_path=paths.normalized_dir,
        )

    with phase_scope(logger, stage="convert_markdown", customer=slug) as scope:
        if safe_list:
            content_mds = _convert_normalized_markdown(paths, book_dir, safe_list, logger=logger)
        else:
            content_mds = cast(List[Path], list_content_markdown(book_dir))
            user_content = [p for p in content_mds if p.name not in {"README.md", "SUMMARY.md"}]
            if not user_content:
                logger.info(
                    "semantic.convert.no_files",
                    extra={"slug": slug, "normalized_dir": str(paths.normalized_dir), "book_dir": str(book_dir)},
                )
                raise ConfigError(
                    "Nessun Markdown valido trovato in normalized/ e nessun contenuto preesistente.",
                    slug=slug,
                    file_path=paths.normalized_dir,
                )

        try:
            scope.set_artifacts(len(content_mds))
        except Exception:
            scope.set_artifacts(None)

        ms = int((time.perf_counter() - start_ts) * 1000)
        if safe_list:
            if content_mds:
                _log_conversion_success(
                    logger,
                    slug,
                    ms=ms,
                    content_count=len(content_mds),
                    mode="convert",
                )
                return content_mds
            raise ConversionError(
                "La conversione non ha prodotto Markdown di contenuto (solo README/SUMMARY).",
                slug=slug,
                file_path=book_dir,
            )

        if discarded_unsafe > 0:
            raise ConfigError(
                (
                    f"Trovati solo Markdown non sicuri/fuori perimetro in normalized (scartati={discarded_unsafe}). "
                    "Rimuovi i symlink o sposta i file reali dentro 'normalized/' e riprova."
                ),
                slug=slug,
                file_path=paths.normalized_dir,
            )

        if content_mds:
            _log_conversion_success(
                logger,
                slug,
                ms=ms,
                content_count=len(content_mds),
                mode="reuse",
                reuse_count=len(content_mds),
            )
            return content_mds

        raise ConfigError(
            f"Nessun Markdown trovato in normalized locale: {paths.normalized_dir}",
            slug=slug,
            file_path=paths.normalized_dir,
        )
