# SPDX-License-Identifier: GPL-3.0-or-later
"""Funzioni di frontmatter/README estratte da semantic.api."""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, cast

from pipeline.content_utils import generate_readme_markdown as _gen_readme
from pipeline.content_utils import generate_summary_markdown as _gen_summary
from pipeline.content_utils import validate_markdown_dir as _validate_md
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from pipeline.frontmatter_utils import dump_frontmatter as _shared_dump_frontmatter
from pipeline.frontmatter_utils import parse_frontmatter as _shared_parse_frontmatter
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within
from semantic.context_paths import resolve_context_paths
from semantic.embedding_service import list_content_markdown
from semantic.entities_frontmatter import enrich_frontmatter_with_entities
from semantic.types import ClientContextProtocol
from storage.tags_store import derive_db_path_from_yaml_path as _derive_tags_db_path
from storage.tags_store import get_conn as _get_tags_conn

__all__ = [
    "enrich_frontmatter",
    "write_summary_and_readme",
    "_build_inverse_index",
    "_merge_frontmatter",
    "_as_list_str",
    "_term_to_pattern",
    "_guess_tags_for_name",
    "_canonicalize_tags",
    "_dump_frontmatter",
    "_parse_frontmatter",
]


def _get_paths(slug: str) -> Dict[str, Path]:
    from semantic.api import get_paths  # import locale per evitare cicli

    return cast(Dict[str, Path], get_paths(slug))


def enrich_frontmatter(
    context: ClientContextProtocol,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Sequence[str]]],
    *,
    slug: str,
    allow_empty_vocab: bool = False,
) -> List[Path]:
    from pipeline.frontmatter_utils import read_frontmatter as _read_fm

    start_ts = time.perf_counter()
    paths = resolve_context_paths(context, slug, paths_provider=_get_paths)
    base_dir, md_dir = paths.base_dir, paths.md_dir
    ensure_within(base_dir, md_dir)

    if not vocab:
        tags_db = Path(_derive_tags_db_path(base_dir / "semantic" / "tags_reviewed.yaml"))
        if not allow_empty_vocab:
            raise ConfigError(
                "Vocabolario canonico assente: impossibile arricchire i front-matter senza tags canonici.",
                slug=slug,
                file_path=tags_db,
            )
        logger.info(
            "semantic.frontmatter.skip_tags",
            extra={"slug": slug, "reason": "empty_vocab_allowed", "file_path": str(tags_db)},
        )

    mds = list_content_markdown(md_dir)
    touched: List[Path] = []
    inv = _build_inverse_index(vocab)

    with phase_scope(logger, stage="enrich_frontmatter", customer=slug) as scope:
        for md in mds:
            name = md.name
            title = re.sub(r"[_\/\-\s]+", " ", Path(name).stem).strip().replace("  ", " ") or "Documento"
            try:
                meta, body = _read_fm(md_dir, md, encoding="utf-8", use_cache=True)
            except OSError as exc:
                logger.warning(
                    "semantic.frontmatter.read_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(exc)},
                )
                continue

            raw_list = _as_list_str(meta.get("tags_raw"))
            canonical_from_raw = _canonicalize_tags(raw_list, inv)
            tags = canonical_from_raw or _guess_tags_for_name(name, vocab, inv=inv)
            new_meta = _merge_frontmatter(meta, title=title, tags=tags)
            # Arricchimento additivo da doc_entities (se presenti e approvate)
            try:
                tags_db = Path(_derive_tags_db_path(base_dir / "semantic" / "tags_reviewed.yaml"))
                if tags_db.exists():
                    with _get_tags_conn(str(tags_db)) as conn:
                        new_meta = enrich_frontmatter_with_entities(
                            new_meta,
                            conn,
                            getattr(paths, "semantic_mapping", {}),
                        )
            except Exception:
                # fail-soft: non bloccare l'arricchimento standard
                pass
            if meta == new_meta:
                continue

            fm = _dump_frontmatter(new_meta)
            try:
                ensure_within(md_dir, md)
                safe_write_text(md, fm + body, encoding="utf-8", atomic=True)
                touched.append(md)
                logger.info(
                    "semantic.frontmatter.updated",
                    extra={
                        "slug": slug,
                        "file_path": str(md),
                        "tags": tags,
                        "tags_raw": raw_list,
                        "canonical_from_raw": canonical_from_raw,
                    },
                )
            except OSError as exc:
                logger.warning(
                    "semantic.frontmatter.write_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(exc)},
                )
        try:
            scope.set_artifacts(len(touched))
        except Exception:
            scope.set_artifacts(None)

    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.enrich_frontmatter.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"updated": len(touched)}},
    )
    return touched


def write_summary_and_readme(context: ClientContextProtocol, logger: logging.Logger, *, slug: str) -> None:
    start_ts = time.perf_counter()
    paths = resolve_context_paths(context, slug, paths_provider=_get_paths)
    md_dir = paths.md_dir
    shim = paths
    summary_func = _gen_summary
    readme_func = _gen_readme
    validate_func = _validate_md

    errors: List[str] = []
    with phase_scope(logger, stage="write_summary_and_readme", customer=slug) as scope:
        try:
            summary_func(shim)
            logger.info(
                "semantic.summary.written",
                extra={"slug": slug, "file_path": str(md_dir / "SUMMARY.md")},
            )
        except Exception as exc:  # pragma: no cover
            summary_path = md_dir / "SUMMARY.md"
            logger.exception(
                "semantic.summary.failed",
                extra={"slug": slug, "file_path": str(summary_path), "error": str(exc)},
            )
            errors.append(f"summary: {exc}")

        try:
            readme_func(shim)
            logger.info(
                "semantic.readme.written",
                extra={"slug": slug, "file_path": str(md_dir / "README.md")},
            )
        except Exception as exc:  # pragma: no cover
            readme_path = md_dir / "README.md"
            logger.error(
                "Generazione README.md fallita",
                extra={"slug": slug, "file_path": str(readme_path)},
            )
            logger.exception(
                "semantic.readme.failed",
                extra={"slug": slug, "file_path": str(readme_path), "error": str(exc)},
            )
            errors.append(f"readme: {exc}")

        if errors:
            raise ConversionError("; ".join(errors), slug=slug, file_path=md_dir)

        validate_func(shim)
        logger.info("semantic.book.validated", extra={"slug": slug, "book_dir": str(md_dir)})
        scope.set_artifacts(2)

    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.summary_readme.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"summary": True, "readme": True}},
    )


# ---------------------------------------------------------------------------
# Helper condivisi con i test esistenti
# ---------------------------------------------------------------------------


def _build_inverse_index(vocab: Dict[str, Dict[str, Sequence[str]]]) -> Dict[str, Set[str]]:
    inverse: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        aliases = meta.get("aliases") or []
        for term in {canon, *aliases}:
            normalized = str(term).strip().lower()
            if normalized:
                inverse.setdefault(normalized, set()).add(canon)
    return inverse


def _as_list_str(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            if item is None:
                continue
            stripped = str(item).strip()
            if stripped:
                out.append(stripped)
        return out
    stripped = str(value).strip()
    return [stripped] if stripped else []


def _merge_frontmatter(existing: Dict[str, Any], *, title: Optional[str], tags: List[str]) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        left = _as_list_str(meta.get("tags"))
        merged = sorted(set([*left, *tags]))
        meta["tags"] = merged
    return meta


@lru_cache(maxsize=1024)
def _term_to_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.strip().lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


def _guess_tags_for_name(
    name_like_path: str,
    vocab: Dict[str, Dict[str, Sequence[str]]],
    *,
    inv: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    if not vocab:
        return []
    if inv is None:
        inv = _build_inverse_index(vocab)
    lowered = name_like_path.lower()
    lowered = re.sub(r"[_\/\-\s]+", " ", lowered)

    found: Set[str] = set()
    for term, canon_set in inv.items():
        if not term:
            continue
        pattern = _term_to_pattern(term)
        if pattern.search(lowered):
            found.update(canon_set)
    return sorted(found)


def _canonicalize_tags(raw_tags: List[str], inv: Dict[str, Set[str]]) -> List[str]:
    canonical: Set[str] = set()
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if not normalized:
            continue
        mapped = inv.get(normalized)
        if mapped:
            canonical.update(mapped)
        else:
            canonical.add(tag.strip())
    return sorted(canonical)


def _parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    meta_raw, body = _shared_parse_frontmatter(md_text)
    meta_dict: Dict[str, Any] = dict(meta_raw or {})
    return meta_dict, body


def _dump_frontmatter(meta: Dict[str, Any]) -> str:
    meta_dict: Dict[str, Any] = dict(meta)
    return cast(str, _shared_dump_frontmatter(meta_dict))
