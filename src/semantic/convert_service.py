# SPDX-License-Identifier: GPL-3.0-or-later
"""Servizi dedicati alla conversione RAW -> Markdown della pipeline semantica."""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, cast
from weakref import WeakKeyDictionary

from pipeline.content_utils import convert_files_to_structured_markdown as _convert_md
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within
from semantic.context_paths import ContextPaths, resolve_context_paths
from semantic.embedding_service import list_content_markdown
from semantic.types import ClientContextProtocol

__all__ = ["convert_markdown", "discover_raw_inputs"]


@dataclass(frozen=True)
class RawDiscovery:
    safe_pdfs: Tuple[Path, ...]
    discarded_unsafe: int


def _get_paths(slug: str) -> Dict[str, Path]:
    from semantic.api import get_paths  # import locale per evitare cicli

    return cast(Dict[str, Path], get_paths(slug))


def convert_markdown(
    context: ClientContextProtocol,
    logger: logging.Logger,
    *,
    slug: str,
) -> List[Path]:
    """Converte i PDF in RAW in Markdown strutturato dentro book/."""
    start_ts = time.perf_counter()
    paths = resolve_context_paths(context, slug, paths_provider=_get_paths)
    base_dir, raw_dir, md_dir = paths.base_dir, paths.raw_dir, paths.md_dir
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, md_dir)

    md_dir.mkdir(parents=True, exist_ok=True)
    shim = paths

    discovery = discover_raw_inputs(raw_dir, logger, slug)
    safe_pdfs = list(discovery.safe_pdfs)
    discarded_unsafe = discovery.discarded_unsafe

    if discarded_unsafe > 0:
        logger.info("semantic.convert.discarded_unsafe", extra={"slug": slug, "count": discarded_unsafe})

    return _run_markdown_conversion(
        shim,
        md_dir,
        logger,
        safe_pdfs=safe_pdfs,
        discarded_unsafe=discarded_unsafe,
        start_ts=start_ts,
    )


def discover_raw_inputs(raw_dir: Path, logger: logging.Logger, slug: str) -> RawDiscovery:
    """Valida RAW e restituisce i PDF sicuri con conteggio scarti."""
    if not raw_dir.exists():
        raise ConfigError(f"Cartella RAW locale non trovata: {raw_dir}", slug=slug, file_path=raw_dir)
    if not raw_dir.is_dir():
        raise ConfigError(f"Percorso RAW non e' una directory: {raw_dir}", slug=slug, file_path=raw_dir)

    safe, discarded = _collect_safe_pdfs(raw_dir, logger, slug)
    return RawDiscovery(safe_pdfs=tuple(safe), discarded_unsafe=discarded)


# ---------------------------------------------------------------------------
# Helpers migrati da semantic/api.py
# ---------------------------------------------------------------------------

_SUPPORTED_SAFE_PDFS: "WeakKeyDictionary[Any, bool]" = WeakKeyDictionary()


class _CallConvert(Protocol):
    def __call__(
        self,
        func: Any,
        ctx: ContextPaths,
        md_dir: Path,
        *,
        safe_pdfs: Optional[List[Path]] = None,
    ) -> None: ...


def _converter_supports_safe_pdfs(func: Any) -> bool:
    try:
        return _SUPPORTED_SAFE_PDFS[func]
    except Exception:
        pass
    try:
        signature = inspect.signature(func)
        supports = "safe_pdfs" in signature.parameters
    except Exception:
        supports = False
    try:
        _SUPPORTED_SAFE_PDFS[func] = supports
    except Exception:
        pass
    return supports


def _call_convert_md(
    func: Any,
    ctx: ContextPaths,
    md_dir: Path,
    *,
    safe_pdfs: Optional[List[Path]] = None,
) -> None:
    """Invoca il converter garantendo un fail-fast coerente se la firma non combacia."""
    if not callable(func):
        raise ConversionError("convert_md target is not callable", slug=ctx.slug, file_path=md_dir)

    kwargs: Dict[str, Any] = {}

    try:
        sig = inspect.signature(func)
    except Exception:
        sig = None

    if sig and "md_dir" in sig.parameters:
        kwargs["md_dir"] = md_dir

    if safe_pdfs is not None:
        if sig is not None:
            supports_safe = "safe_pdfs" in sig.parameters
            try:
                _SUPPORTED_SAFE_PDFS[func] = supports_safe
            except Exception:
                pass
        else:
            supports_safe = _converter_supports_safe_pdfs(func)
        if supports_safe:
            kwargs["safe_pdfs"] = safe_pdfs

    try:
        func(ctx, **kwargs)
    except TypeError as exc:
        raise ConversionError(f"convert_md call failed: {exc}", slug=ctx.slug, file_path=md_dir) from exc


def _collect_safe_pdfs(raw_dir: Path, logger: logging.Logger, slug: str) -> Tuple[List[Path], int]:
    """Raccoglie PDF sicuri sotto raw_dir rispettando la path-safety della pipeline."""
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

    for safe_path in ppath.iter_safe_pdfs(raw_dir, on_skip=_on_skip, use_cache=True):
        safe.append(safe_path)

    return safe, discarded


def _log_conversion_success(
    logger: logging.Logger,
    slug: str,
    *,
    ms: int,
    content_count: int,
    mode: str,
    reuse_count: Optional[int] = None,
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
    shim: ContextPaths,
    md_dir: Path,
    logger: logging.Logger,
    *,
    safe_pdfs: Sequence[Path],
    discarded_unsafe: int,
    start_ts: float,
) -> List[Path]:

    slug = shim.slug
    if safe_pdfs:
        safe_list = list(safe_pdfs)
    else:
        safe_list = []

    with phase_scope(logger, stage="convert_markdown", customer=slug) as scope:
        call_convert = _call_convert_md

        if safe_list:
            call_convert(_convert_md, shim, md_dir, safe_pdfs=safe_list)
            content_mds = cast(List[Path], list_content_markdown(md_dir))
        else:
            content_mds = cast(List[Path], list_content_markdown(md_dir))
            if not content_mds:
                logger.info(
                    "semantic.convert.no_files",
                    extra={"slug": slug, "raw_dir": str(shim.raw_dir), "book_dir": str(md_dir)},
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
                file_path=md_dir,
            )

        if discarded_unsafe > 0:
            raise ConfigError(
                (
                    f"Trovati solo PDF non sicuri/fuori perimetro in RAW (scartati={discarded_unsafe}). "
                    "Rimuovi i symlink o sposta i PDF reali dentro 'raw/' e riprova."
                ),
                slug=slug,
                file_path=shim.raw_dir,
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

        raise ConfigError(f"Nessun PDF trovato in RAW locale: {shim.raw_dir}", slug=slug, file_path=shim.raw_dir)
