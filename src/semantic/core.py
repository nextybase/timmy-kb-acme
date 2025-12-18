# SPDX-License-Identifier: GPL-3.0-only
"""Canonical semantic helpers for vision ingestion and extraction."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from pipeline.exceptions import InputDirectoryMissing, PipelineError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import is_safe_subpath, iter_safe_paths, read_text_safe
from semantic.document_ingest import DocumentContent, read_document
from semantic.vocab_loader import load_reviewed_vocab

_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}


def compile_document_to_vision_yaml(source_path: Path, yaml_path: Path) -> None:
    doc: DocumentContent = read_document(source_path)
    payload = {
        "version": 1,
        "metadata": {
            "source_pdf_path": str(Path(doc.metadata.get("source_path", source_path))),
            "source_pdf_sha256": doc.metadata.get("sha256", ""),
        },
        "content": {
            "pages": doc.text_blocks,
            "full_text": "\n\n".join(doc.text_blocks),
        },
    }
    yaml_str = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(yaml_path, yaml_str)


def compile_pdf_to_yaml(pdf_path: Path, yaml_path: Path) -> None:
    return compile_document_to_vision_yaml(pdf_path, yaml_path)


class _CtxProto:
    base_dir: Path
    md_dir: Path
    slug: Optional[str]


def _list_markdown_files(context: _CtxProto, logger: logging.Logger) -> List[Path]:
    if not getattr(context, "md_dir", None) or not getattr(context, "base_dir", None):
        raise PipelineError("Contesto incompleto: md_dir/base_dir mancanti", slug=getattr(context, "slug", None))
    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PipelineError("Path non sicuro", slug=context.slug, file_path=context.md_dir)
    if not context.md_dir.exists() or not context.md_dir.is_dir():
        raise InputDirectoryMissing(f"Directory markdown non valida: {context.md_dir}", slug=context.slug)
    files = sorted(
        iter_safe_paths(
            context.md_dir,
            include_dirs=False,
            include_files=True,
            suffixes=(".md",),
        ),
        key=lambda p: p.relative_to(context.md_dir).as_posix().lower(),
    )
    logger.info(
        "semantic.files.found",
        extra={
            "slug": context.slug,
            "file_path": str(context.md_dir),
            "count": len(files),
        },
    )
    return files


def _normalize_term(term: str) -> str:
    t = unicodedata.normalize("NFC", term.strip())
    return re.sub(r"[\u200B\u200C\u200D\uFEFF]", "", t)


def _term_to_pattern(term: str) -> re.Pattern[str]:
    esc = re.escape(_normalize_term(term).lower()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){esc}(?!\w)")


def _sanitize_kw(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch not in _ZERO_WIDTH)
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _sanitize_and_dedup_mapping(mapping: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for concept, values in (mapping or {}).items():
        seen: set[str] = set()
        items: List[str] = []
        for raw in values or []:
            candidate = _sanitize_kw(str(raw))
            if not candidate:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(candidate)
        out[str(concept)] = items
    return out


def load_semantic_mapping(context: _CtxProto, logger: Optional[logging.Logger] = None) -> Dict[str, List[str]]:
    base_dir = getattr(context, "base_dir", None)
    if base_dir is None:
        raise PipelineError("Context privo di base_dir per estrazione semantica.", slug=getattr(context, "slug", None))
    log = logger or get_structured_logger("semantic.extraction", context=context)
    vocab = load_reviewed_vocab(base_dir, log)
    if not vocab:
        raise PipelineError(
            "Vocabolario canonico assente: esegui l'estrazione tag",
            slug=getattr(context, "slug", None),
        )
    mapping: Dict[str, List[str]] = {}
    for canon, payload in vocab.items():
        aliases = payload.get("aliases") or []
        normalized_aliases = [str(alias) for alias in aliases]
        normalized_aliases.append(str(canon))
        mapping[str(canon)] = normalized_aliases
    return _sanitize_and_dedup_mapping(mapping)


def extract_semantic_concepts(
    context: _CtxProto, *, max_scan_bytes: Optional[int] = None
) -> Dict[str, List[Dict[str, str]]]:
    logger = get_structured_logger("semantic.extract", context=context)
    mapping = load_semantic_mapping(context)
    if not mapping:
        logger.warning("semantic.extract.mapping_empty", extra={"slug": context.slug})
        return {}
    files = _list_markdown_files(context, logger)
    extracted: Dict[str, List[Dict[str, str]]] = {}
    for concept, keywords in mapping.items():
        if not keywords:
            extracted[concept] = []
            continue
        norm_kws: List[str] = []
        seen: set[str] = set()
        for kw in keywords:
            normalized = _normalize_term(kw)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            norm_kws.append(normalized)
        patterns = [_term_to_pattern(k) for k in norm_kws]
        matches: List[Dict[str, str]] = []
        for file in files:
            try:
                if max_scan_bytes is not None and file.stat().st_size > max_scan_bytes:
                    logger.info(
                        "semantic.extract.skip_large_md",
                        extra={
                            "slug": context.slug,
                            "file_path": str(file),
                            "bytes": file.stat().st_size,
                            "limit": max_scan_bytes,
                        },
                    )
                    continue
                content = read_text_safe(context.md_dir, file, encoding="utf-8")
                normalized_content = re.sub(
                    r"[\u200B\u200C\u200D\uFEFF]",
                    "",
                    unicodedata.normalize("NFC", content),
                ).lower()
                hit_idx: Optional[int] = None
                for i, pat in enumerate(patterns):
                    if pat.search(normalized_content):
                        hit_idx = i
                        break
                if hit_idx is not None:
                    matches.append({"file": file.name, "keyword": norm_kws[hit_idx]})
            except Exception as exc:
                logger.warning(
                    "semantic.extract.read_failed",
                    extra={"slug": context.slug, "file_path": str(file), "error": str(exc)},
                )
        extracted[concept] = matches
    logger.info("semantic.extract.completed", extra={"slug": context.slug})
    return extracted


def _enrich_md(context: _CtxProto, file: Path, logger: logging.Logger) -> None:
    logger.debug("semantic.enrich.file_start", extra={"slug": context.slug, "file_path": str(file)})


def enrich_markdown_folder(context: _CtxProto, logger: Optional[logging.Logger] = None) -> None:
    logger = logger or get_structured_logger("semantic.enrich", context=context)
    if not getattr(context, "enrich_enabled", True):
        logger.info("enrich.disabled", extra={"slug": context.slug})
        return
    files = _list_markdown_files(context, logger)
    logger.info(
        "semantic.enrich.start",
        extra={
            "slug": context.slug,
            "file_path": str(context.md_dir),
            "count": len(files),
        },
    )
    for file in files:
        try:
            _enrich_md(context, file, logger)
        except Exception:
            pass
    logger.info("semantic.enrich.completed", extra={"slug": context.slug})


__all__ = [
    "compile_document_to_vision_yaml",
    "compile_pdf_to_yaml",
    "extract_semantic_concepts",
    "enrich_markdown_folder",
    "load_semantic_mapping",
]
