# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/api.py
from __future__ import annotations

import inspect
import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set, Tuple, cast
from weakref import WeakKeyDictionary

from kb_db import get_db_path as _get_db_path
from kb_db import init_db as _init_kb_db
from kb_db import insert_chunks as _insert_chunks
from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.content_utils import convert_files_to_structured_markdown as _convert_md
from pipeline.content_utils import generate_readme_markdown as _gen_readme
from pipeline.content_utils import generate_summary_markdown as _gen_summary
from pipeline.content_utils import validate_markdown_dir as _validate_md
from pipeline.embedding_utils import normalize_embeddings
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, iter_safe_paths, sorted_paths, validate_slug
from semantic.auto_tagger import extract_semantic_candidates as _extract_candidates
from semantic.auto_tagger import render_tags_csv as _render_tags_csv
from semantic.config import load_semantic_config as _load_semantic_config
from semantic.normalizer import normalize_tags as _normalize_tags
from semantic.tags_extractor import copy_local_pdfs_to_raw as _copy_local_pdfs_to_raw
from semantic.tags_io import write_tagging_readme as _write_tagging_readme
from semantic.tags_io import write_tags_reviewed_from_nlp_db as _write_tags_yaml_from_db
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab
from storage.tags_store import derive_db_path_from_yaml_path as _derive_tags_db_path
from storage.tags_store import ensure_schema_v2 as _ensure_tags_schema_v2
from storage.tags_store import get_conn as _get_tags_conn

if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType
else:
    from semantic.types import ClientContextProtocol as ClientContextType

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
    "build_tags_csv",
    "build_markdown_book",
    "index_markdown_to_db",
    "copy_local_pdfs_to_raw",
    "list_content_markdown",
    "export_tags_yaml_from_db",
]


def get_paths(slug: str) -> Dict[str, Path]:
    safe_slug = validate_slug(slug)
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{safe_slug}"
    return {
        "base": base_dir,
        "raw": base_dir / "raw",
        "book": base_dir / "book",
        "semantic": base_dir / "semantic",
    }


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    return cast(Dict[str, Dict[str, Set[str]]], _load_reviewed_vocab(base_dir, logger))


def _require_reviewed_vocab(
    base_dir: Path,
    logger: logging.Logger,
    *,
    slug: str,
) -> Dict[str, Dict[str, Set[str]]]:
    """Restituisce il vocabolario canonico o solleva ConfigError se assente."""
    global _LAST_VOCAB_STUBBED
    vocab = load_reviewed_vocab(base_dir, logger)
    if vocab:
        _LAST_VOCAB_STUBBED = False
        return vocab
    loader_module = getattr(_load_reviewed_vocab, "__module__", "")
    if loader_module != "semantic.vocab_loader":
        _LAST_VOCAB_STUBBED = True
        logger.info(
            "semantic.vocab.stubbed",
            extra={"slug": slug, "loader_module": loader_module},
        )
        return {}
    _LAST_VOCAB_STUBBED = False
    tags_db = Path(_derive_tags_db_path(base_dir / "semantic" / "tags_reviewed.yaml"))
    raise ConfigError(
        "Vocabolario canonico assente. Esegui l'estrazione tag per popolare semantic/tags.db.",
        slug=slug,
        file_path=tags_db,
    )


class _CtxShim:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str

    def __init__(self, *, base_dir: Path, raw_dir: Path, md_dir: Path, slug: str) -> None:
        self.base_dir = base_dir
        self.raw_dir = raw_dir
        self.md_dir = md_dir
        self.slug = slug


def _resolve_ctx_paths(context: ClientContextType, slug: str) -> tuple[Path, Path, Path]:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or (base_dir / "raw"))
    md_dir = cast(Path, getattr(context, "md_dir", None) or (base_dir / "book"))
    return base_dir, raw_dir, md_dir


# --- feature detection cache per il converter (evita inspect ripetuti) ---
_SUPPORTED_SAFE_PDFS: "WeakKeyDictionary[Any, bool]" = WeakKeyDictionary()
_LAST_VOCAB_STUBBED = False


def _converter_supports_safe_pdfs(func: Any) -> bool:
    try:
        return _SUPPORTED_SAFE_PDFS[func]
    except Exception:
        pass
    try:
        sig = inspect.signature(func)
        supports = "safe_pdfs" in sig.parameters
    except Exception:
        supports = False
    try:
        _SUPPORTED_SAFE_PDFS[func] = supports
    except Exception:
        # best-effort: se non possiamo cache-are (oggetti non weakref-abili), ignora
        pass
    return supports


def _call_convert_md(
    func: Any,
    ctx: _CtxShim,
    md_dir: Path,
    *,
    safe_pdfs: list[Path] | None = None,
) -> None:
    """Invoca il converter garantendo un fail-fast coerente se la firma è incompatibile.

    Passa `safe_pdfs` solo se:
      - è stato calcolato a monte (non None)
      - la funzione target accetta il parametro (retro-compatibilità).
    """
    if not callable(func):
        raise ConversionError("convert_md target is not callable", slug=ctx.slug, file_path=md_dir)

    kwargs: Dict[str, Any] = {}

    # Ispezione UNA VOLTA e cache per safe_pdfs
    sig: inspect.Signature | None
    try:
        sig = inspect.signature(func)
    except Exception:
        sig = None

    # molti converter già accettano md_dir come keyword
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
    except TypeError as e:
        # Wrappa i TypeError (firma non compatibile) in ConversionError con contesto
        raise ConversionError(f"convert_md call failed: {e}", slug=ctx.slug, file_path=md_dir) from e


# ---------------------------
# Helper DRY / SRP (PR1)
# ---------------------------
def _collect_safe_pdfs(raw_dir: Path, logger: logging.Logger, slug: str) -> tuple[list[Path], int]:
    """Raccoglie PDF sotto raw_dir applicando path-safety forte e scartando symlink/percorsi insicuri.

    Restituisce (lista_pdf_sicuri, conteggio_scartati).
    Log coerenti con semantic.convert.skip_symlink / semantic.convert.skip_unsafe.
    """
    # Import runtime per consentire ai test di monkeypatchare path_utils.ensure_within_and_resolve
    from pipeline import path_utils as ppath

    safe: list[Path] = []
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

    for safe_path in ppath.iter_safe_pdfs(raw_dir, on_skip=_on_skip):
        safe.append(safe_path)
    return safe, discarded


def list_content_markdown(book_dir: Path) -> list[Path]:
    """Elenco dei Markdown 'di contenuto' in book_dir, escludendo README/SUMMARY."""
    return [
        p
        for p in sorted_paths(
            iter_safe_paths(book_dir, include_dirs=False, include_files=True, suffixes=(".md",)), base=book_dir
        )
        if p.name.lower() not in {"readme.md", "summary.md"}
    ]


@dataclass(frozen=True)
class _RawDiscovery:
    safe_pdfs: tuple[Path, ...]
    discarded_unsafe: int


@dataclass(frozen=True)
class _CollectedMarkdown:
    contents: list[str]
    rel_paths: list[str]
    frontmatters: list[Dict[str, Any]]
    skipped_io: int
    skipped_empty: int
    total_files: int


@dataclass(frozen=True)
class _EmbeddingResult:
    contents: list[str]
    rel_paths: list[str]
    frontmatters: list[Dict[str, Any]]
    embeddings: list[list[float]]
    vectors_empty: int


def _discover_raw_inputs(raw_dir: Path, logger: logging.Logger, slug: str) -> _RawDiscovery:
    """Valida `raw_dir` e restituisce i PDF sicuri insieme al conteggio scartati."""
    if not raw_dir.exists():
        raise ConfigError(f"Cartella RAW locale non trovata: {raw_dir}", slug=slug, file_path=raw_dir)
    if not raw_dir.is_dir():
        raise ConfigError(f"Percorso RAW non è una directory: {raw_dir}", slug=slug, file_path=raw_dir)
    safe_pdfs, discarded = _collect_safe_pdfs(raw_dir, logger, slug)
    return _RawDiscovery(safe_pdfs=tuple(safe_pdfs), discarded_unsafe=discarded)


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
    shim: _CtxShim,
    md_dir: Path,
    logger: logging.Logger,
    *,
    safe_pdfs: Sequence[Path],
    discarded_unsafe: int,
    start_ts: float,
) -> List[Path]:
    slug = shim.slug
    with phase_scope(logger, stage="convert_markdown", customer=slug) as m:
        if safe_pdfs:
            safe_list = list(safe_pdfs)
            _call_convert_md(_convert_md, shim, md_dir, safe_pdfs=safe_list)
            content_mds = list_content_markdown(md_dir)
        else:
            content_mds = list_content_markdown(md_dir)
            if not content_mds:
                logger.info(
                    "semantic.convert.no_files",
                    extra={"slug": slug, "raw_dir": str(shim.raw_dir), "book_dir": str(md_dir)},
                )

        try:
            m.set_artifacts(len(content_mds))
        except Exception:
            m.set_artifacts(None)

        ms = int((time.perf_counter() - start_ts) * 1000)
        if safe_pdfs:
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


def _collect_markdown_inputs(
    book_dir: Path,
    files: Sequence[Path],
    logger: logging.Logger,
    slug: str,
) -> _CollectedMarkdown:
    from pipeline.path_utils import read_text_safe

    contents: list[str] = []
    rel_paths: list[str] = []
    frontmatters: list[Dict[str, Any]] = []
    skipped_io = 0
    skipped_empty = 0

    for f in files:
        try:
            text = read_text_safe(book_dir, f, encoding="utf-8")
        except Exception as exc:
            logger.warning(
                "semantic.index.read_failed",
                extra={"slug": slug, "file_path": str(f), "error": str(exc)},
            )
            skipped_io += 1
            continue
        meta, body = _parse_frontmatter(text)
        payload = (body or "").lstrip("\ufeff").strip()
        if not payload:
            payload = text.strip()
        if not payload:
            logger.info(
                "semantic.index.skip_empty_file",
                extra={"slug": slug, "file_path": str(f)},
            )
            skipped_empty += 1
            continue
        contents.append(payload)
        rel_paths.append(f.relative_to(book_dir).as_posix())
        frontmatters.append(dict(meta or {}))

    return _CollectedMarkdown(
        contents=contents,
        rel_paths=rel_paths,
        frontmatters=frontmatters,
        skipped_io=skipped_io,
        skipped_empty=skipped_empty,
        total_files=len(files),
    )


def _compute_embeddings_for_markdown(
    collected: _CollectedMarkdown,
    embeddings_client: _EmbeddingsClient,
    logger: logging.Logger,
    slug: str,
) -> tuple[Optional[_EmbeddingResult], int]:
    if not collected.contents:
        return None, 0

    try:
        vecs_raw = embeddings_client.embed_texts(collected.contents)
    except Exception as exc:
        logger.error(
            "semantic.index.embedding_error",
            extra={"slug": slug, "error": str(exc), "count": len(collected.contents)},
        )
        raise

    vecs = normalize_embeddings(vecs_raw)
    vectors_empty = 0

    if len(vecs) == 0:
        logger.warning("semantic.index.no_embeddings", extra={"slug": slug, "count": 0})
        return None, 0

    contents = list(collected.contents)
    rel_paths = list(collected.rel_paths)
    frontmatters = list(collected.frontmatters)

    original_contents_len = len(contents)
    original_embeddings_len = len(vecs)

    if original_embeddings_len != original_contents_len:
        logger.warning(
            "semantic.index.mismatched_embeddings",
            extra={"slug": slug, "embeddings": original_embeddings_len, "contents": original_contents_len},
        )
        min_len = min(original_embeddings_len, original_contents_len)
        dropped_mismatch = (original_contents_len - min_len) + (original_embeddings_len - min_len)
        if dropped_mismatch > 0:
            logger.info(
                "semantic.index.embedding_pruned",
                extra={
                    "slug": slug,
                    "cause": "mismatch",
                    "dropped": int(dropped_mismatch),
                    "kept": int(min_len),
                    "contents": int(original_contents_len),
                    "embeddings": int(original_embeddings_len),
                },
            )
        vectors_empty += max(0, dropped_mismatch)
        contents = contents[:min_len]
        rel_paths = rel_paths[:min_len]
        vecs = vecs[:min_len]
        frontmatters = frontmatters[:min_len]

    original_candidate_count = len(contents)
    filtered_contents: list[str] = []
    filtered_paths: list[str] = []
    filtered_vecs: list[list[float]] = []
    filtered_fronts: list[Dict[str, Any]] = []

    for text, rel_name, emb, meta in zip(contents, rel_paths, vecs, frontmatters, strict=False):
        if len(emb) == 0:
            continue
        filtered_contents.append(text)
        filtered_paths.append(rel_name)
        filtered_vecs.append(list(emb))
        filtered_fronts.append(meta)

    dropped_empty = original_candidate_count - len(filtered_contents)
    if dropped_empty > 0 and len(filtered_contents) == 0:
        logger.warning(
            "semantic.index.first_embedding_empty",
            extra={"slug": slug, "cause": "empty_embedding"},
        )
        logger.warning(
            "semantic.index.all_embeddings_empty",
            extra={"event": "semantic.index.all_embeddings_empty", "slug": slug, "count": len(vecs)},
        )
        vectors_empty += max(0, dropped_empty)
        return None, vectors_empty

    if dropped_empty > 0:
        logger.info(
            "semantic.index.embedding_pruned",
            extra={
                "slug": slug,
                "cause": "empty_embedding",
                "dropped": int(dropped_empty),
                "kept": int(len(filtered_contents)),
                "candidates": int(original_candidate_count),
            },
        )
    vectors_empty += max(0, dropped_empty)

    return (
        _EmbeddingResult(
            contents=filtered_contents,
            rel_paths=filtered_paths,
            frontmatters=filtered_fronts,
            embeddings=filtered_vecs,
            vectors_empty=vectors_empty,
        ),
        vectors_empty,
    )


def _persist_markdown_embeddings(
    result: _EmbeddingResult,
    *,
    scope: str,
    slug: str,
    db_path: Path | None,
    logger: logging.Logger,
) -> int:
    from datetime import datetime as _dt

    version = _dt.utcnow().strftime("%Y%m%d")
    inserted_total = 0
    for text, rel_name, emb, meta in zip(
        result.contents, result.rel_paths, result.embeddings, result.frontmatters, strict=False
    ):
        payload_meta: Dict[str, Any] = {"file": rel_name}
        if isinstance(meta, dict):
            filtered_meta = {k: v for k, v in meta.items() if v not in (None, "", [], {})}
            payload_meta.update(filtered_meta)
        inserted_total += _insert_chunks(
            project_slug=slug,
            scope=scope,
            path=rel_name,
            version=version,
            meta_dict=payload_meta,
            chunks=[text],
            embeddings=[list(emb)],
            db_path=db_path,
            ensure_schema=False,
        )

    logger.info(
        "semantic.index.completed",
        extra={"slug": slug, "inserted": inserted_total, "files": len(result.rel_paths)},
    )
    return inserted_total


def _log_index_skips(
    logger: logging.Logger,
    slug: str,
    *,
    skipped_io: int,
    skipped_empty: int,
    vectors_empty: int,
) -> None:
    if skipped_io > 0 or skipped_empty > 0 or vectors_empty > 0:
        logger.info(
            "semantic.index.skips",
            extra={
                "slug": slug,
                "skipped_io": int(skipped_io),
                "skipped_no_text": int(skipped_empty),
                "vectors_empty": int(vectors_empty),
            },
        )


def convert_markdown(context: ClientContextType, logger: logging.Logger, *, slug: str) -> List[Path]:
    """Converte i PDF in RAW in Markdown strutturato dentro book/.

    Regole:
    - Se RAW **non esiste** -> ConfigError.
    - Se RAW **non contiene PDF**:
        - NON invocare il converter (evita segnaposto).
        - Se in book/ ci sono Markdown di contenuto -> restituiscili.
        - Altrimenti -> ConfigError (fail-fast).
    - Se RAW **contiene PDF** -> invoca sempre il converter.
    """
    start_ts = time.perf_counter()
    base_dir, raw_dir, md_dir = _resolve_ctx_paths(context, slug)
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, md_dir)

    md_dir.mkdir(parents=True, exist_ok=True)
    shim = _CtxShim(base_dir=base_dir, raw_dir=raw_dir, md_dir=md_dir, slug=slug)

    discovery = _discover_raw_inputs(raw_dir, logger, slug)
    safe_pdfs = discovery.safe_pdfs
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


def enrich_frontmatter(
    context: ClientContextType,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
    allow_empty_vocab: bool = False,
) -> List[Path]:
    from pipeline.path_utils import read_text_safe

    start_ts = time.perf_counter()
    base_dir, raw_dir, md_dir = _resolve_ctx_paths(context, slug)  # noqa: F841
    ensure_within(base_dir, md_dir)

    if not vocab:
        tags_db = Path(_derive_tags_db_path(base_dir / "semantic" / "tags_reviewed.yaml"))
        if not allow_empty_vocab:
            raise ConfigError(
                "Vocabolario canonico assente: impossibile arricchire i front-matter senza tags canonici.",
                slug=slug,
                file_path=tags_db,
            )
        if logger is not None:
            logger.info(
                "semantic.frontmatter.skip_tags",
                extra={"slug": slug, "reason": "empty_vocab_allowed", "file_path": str(tags_db)},
            )

    mds = sorted_paths(md_dir.glob("*.md"), base=md_dir)
    touched: List[Path] = []
    inv = _build_inverse_index(vocab)

    with phase_scope(logger, stage="enrich_frontmatter", customer=slug) as m:
        for md in mds:
            name = md.name
            title = re.sub(r"[_\/\-\s]+", " ", Path(name).stem).strip().replace("  ", " ") or "Documento"
            try:
                text = read_text_safe(md_dir, md, encoding="utf-8")
            except OSError as e:
                logger.warning(
                    "semantic.frontmatter.read_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(e)},
                )
                continue
            meta, body = _parse_frontmatter(text)
            raw_list = _as_list_str(meta.get("tags_raw"))
            canonical_from_raw = _canonicalize_tags(raw_list, inv)
            tags = canonical_from_raw or _guess_tags_for_name(name, vocab, inv=inv)
            new_meta = _merge_frontmatter(meta, title=title, tags=tags)
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
            except OSError as e:
                logger.warning(
                    "semantic.frontmatter.write_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(e)},
                )
        try:
            m.set_artifacts(len(touched))
        except Exception:
            m.set_artifacts(None)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.enrich_frontmatter.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"updated": len(touched)}},
    )
    return touched


def write_summary_and_readme(context: ClientContextType, logger: logging.Logger, *, slug: str) -> None:
    start_ts = time.perf_counter()
    base_dir, raw_dir, md_dir = _resolve_ctx_paths(context, slug)
    shim = _CtxShim(base_dir=base_dir, raw_dir=raw_dir, md_dir=md_dir, slug=slug)

    errors: list[str] = []
    with phase_scope(logger, stage="write_summary_and_readme", customer=slug) as m:
        # SUMMARY
        try:
            _gen_summary(shim)
            logger.info(
                "semantic.summary.written",
                extra={"slug": slug, "file_path": str(md_dir / "SUMMARY.md")},
            )
        except Exception as e:  # pragma: no cover
            summary_path = md_dir / "SUMMARY.md"
            # Evento strutturato con stacktrace
            logger.exception(
                "semantic.summary.failed",
                extra={"slug": slug, "file_path": str(summary_path), "error": str(e)},
            )
            errors.append(f"summary: {e}")

        # README
        try:
            _gen_readme(shim)
            logger.info(
                "semantic.readme.written",
                extra={"slug": slug, "file_path": str(md_dir / "README.md")},
            )
        except Exception as e:  # pragma: no cover
            readme_path = md_dir / "README.md"
            # Compat test legacy (se in futuro ci fosse un test analogo)
            logger.error(
                "Generazione README.md fallita",
                extra={"slug": slug, "file_path": str(readme_path)},
            )
            logger.exception(
                "semantic.readme.failed",
                extra={"slug": slug, "file_path": str(readme_path), "error": str(e)},
            )
            errors.append(f"readme: {e}")

        if errors:
            raise ConversionError("; ".join(errors), slug=slug, file_path=md_dir)

        _validate_md(shim)
        logger.info("semantic.book.validated", extra={"slug": slug, "book_dir": str(md_dir)})
        m.set_artifacts(2)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.summary_readme.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"summary": True, "readme": True}},
    )


def build_tags_csv(context: ClientContextType, logger: logging.Logger, *, slug: str) -> Path:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or paths["raw"])
    semantic_dir = base_dir / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    ensure_within(semantic_dir, csv_path)

    semantic_dir.mkdir(parents=True, exist_ok=True)
    with phase_scope(logger, stage="build_tags_csv", customer=slug) as m:
        cfg = _load_semantic_config(base_dir)
        candidates = _extract_candidates(raw_dir, cfg)
        candidates = _normalize_tags(candidates, cfg.mapping)

        # Arricchimento con top-terms NLP (se disponibili in tags.db)
        try:
            tags_db_path = Path(_derive_tags_db_path(semantic_dir / "tags_reviewed.yaml"))
            folder_terms: Dict[str, List[str]] = {}
            if tags_db_path.exists():
                _ensure_tags_schema_v2(str(tags_db_path))
                with _get_tags_conn(str(tags_db_path)) as conn:
                    rows = conn.execute(
                        """
                        SELECT f.path AS folder_path, t.canonical AS term, SUM(ft.weight) AS weight
                        FROM folder_terms ft
                        JOIN folders f ON f.id = ft.folder_id
                        JOIN terms   t ON t.id = ft.term_id
                        GROUP BY f.path, t.canonical
                        ORDER BY f.path, weight DESC
                        """
                    ).fetchall()
                for row in rows:
                    folder_path = str(row["folder_path"] or "")
                    canonical = str(row["term"] or "").strip()
                    if not canonical:
                        continue
                    rel_folder = folder_path[4:] if folder_path.startswith("raw/") else folder_path
                    rel_folder = rel_folder.strip("/")
                    folder_terms.setdefault(rel_folder, []).append(canonical)

            if folder_terms:
                for rel_path, meta in candidates.items():
                    rel_folder = Path(rel_path).parent.as_posix()
                    rel_folder = "" if rel_folder == "." else rel_folder
                    nlp_tags = folder_terms.get(rel_folder)
                    if not nlp_tags:
                        continue
                    existing = list(meta.get("tags") or [])
                    seen_lower = {str(tag).strip().lower() for tag in existing if str(tag).strip()}
                    enriched: list[str] = list(existing)
                    for term in nlp_tags:
                        term_norm = str(term).strip()
                        if not term_norm:
                            continue
                        key = term_norm.lower()
                        if key in seen_lower:
                            continue
                        enriched.append(term_norm)
                        seen_lower.add(key)
                        if len(enriched) >= 16:
                            break
                    if enriched:
                        meta["tags"] = enriched
        except Exception as exc:
            logger.warning(
                "semantic.tags_csv.enrichment_failed",
                extra={"slug": slug, "error": str(exc)},
                exc_info=True,
            )
            # Se l'arricchimento fallisce, continuiamo con i soli candidati euristici.

        _render_tags_csv(candidates, csv_path, base_dir=base_dir)
        count = len(candidates)
        logger.info(
            "semantic.tags_csv.built",
            extra={"slug": slug, "file_path": str(csv_path), "count": count},
        )
        _write_tagging_readme(semantic_dir, logger)
        try:
            m.set_artifacts(count)
        except Exception:
            m.set_artifacts(None)
    return csv_path


def export_tags_yaml_from_db(
    semantic_dir: Path,
    db_path: Path,
    logger: Any,
    *,
    limit: int = 200,
    min_weight: float = 0.0,
    keep_only_listed: bool = True,
    version: str = "2",
) -> Path:
    """Facade sicuro per esportare tags_reviewed.yaml dal DB NLP (UI-only)."""
    semantic_dir_path = ensure_within_and_resolve(Path(semantic_dir).parent, Path(semantic_dir))
    expected_db_path = ensure_within_and_resolve(
        semantic_dir_path.parent, Path(_derive_tags_db_path(semantic_dir_path / "tags_reviewed.yaml"))
    )
    actual_db_path = Path(db_path).resolve()
    if actual_db_path != expected_db_path:
        raise ConfigError(
            "Percorso DB non coerente con la directory semantic specificata.",
            file_path=str(actual_db_path),
        )
    result = _write_tags_yaml_from_db(
        semantic_dir_path,
        expected_db_path,
        logger,
        limit=limit,
        min_weight=min_weight,
        keep_only_listed=keep_only_listed,
        version=version,
    )
    return cast(Path, result)


def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger: logging.Logger) -> int:
    return int(_copy_local_pdfs_to_raw(src_dir, raw_dir, logger))


def build_markdown_book(context: ClientContextType, logger: logging.Logger, *, slug: str) -> list[Path]:
    """Fase unica che copre conversione, summary/readme e arricchimento frontmatter."""
    if logger is None:
        logger = get_structured_logger("semantic.book", context={"slug": slug})
    start_ts = time.perf_counter()
    with phase_scope(logger, stage="build_markdown_book", customer=slug) as m:
        ctx_base = cast(Path, getattr(context, "base_dir", None))
        base_dir = ctx_base if ctx_base is not None else get_paths(slug)["base"]

        mds = convert_markdown(context, logger, slug=slug)
        write_summary_and_readme(context, logger, slug=slug)
        vocab_missing = False
        vocab: Dict[str, Dict[str, Set[str]]] | None
        try:
            vocab = _require_reviewed_vocab(base_dir, logger, slug=slug)
        except ConfigError as exc:
            vocab_missing = True
            logger.warning(
                "semantic.book.vocab_missing",
                extra={
                    "slug": slug,
                    "error": str(exc),
                    "file_path": getattr(exc, "file_path", None),
                },
            )
            vocab = {}
        if not vocab_missing and (vocab or not _LAST_VOCAB_STUBBED):
            enrich_frontmatter(context, logger, vocab, slug=slug)
        try:
            # Artifacts = numero di MD di contenuto (coerente con convert_markdown)
            m.set_artifacts(len(mds))
        except Exception:
            m.set_artifacts(None)
    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.book.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"content_files": len(mds)}},
    )
    return mds


def index_markdown_to_db(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    scope: str = "book",
    embeddings_client: _EmbeddingsClient,
    db_path: Path | None = None,
) -> int:
    """Indicizza i Markdown presenti in `book/` nel DB con embeddings."""
    start_ts = time.perf_counter()
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    book_dir = cast(Path, getattr(context, "md_dir", None) or paths["book"])
    ensure_within(base_dir, book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)

    files = list_content_markdown(book_dir)
    if not files:
        with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as m:
            logger.info("semantic.index.no_files", extra={"slug": slug, "book_dir": str(book_dir)})
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
        ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "semantic.index.done",
            extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": 0}},
        )
        return 0

    total_files = len(files)
    logger.info(
        "semantic.index.collect.start",
        extra={"slug": slug, "files": total_files},
    )
    collected = _collect_markdown_inputs(book_dir, files, logger, slug)
    logger.info(
        "semantic.index.collect.done",
        extra={
            "slug": slug,
            "files": total_files,
            "usable": len(collected.contents),
            "skipped_io": collected.skipped_io,
            "skipped_no_text": collected.skipped_empty,
        },
    )

    if not collected.contents:
        with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as m:
            logger.info("semantic.index.no_valid_contents", extra={"slug": slug, "book_dir": str(book_dir)})
            _log_index_skips(
                logger,
                slug,
                skipped_io=collected.skipped_io,
                skipped_empty=collected.skipped_empty,
                vectors_empty=0,
            )
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
        ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "semantic.index.done",
            extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": total_files}},
        )
        return 0

    with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as m:
        try:
            _init_kb_db(db_path)
        except Exception as exc:
            try:
                effective = _get_db_path() if db_path is None else Path(db_path).resolve()
            except Exception:
                effective = db_path or Path("data/kb.sqlite")
            raise ConfigError(
                f"Inizializzazione DB fallita: {exc}",
                slug=slug,
                file_path=effective,
            ) from exc

        logger.info(
            "semantic.index.embed.start",
            extra={"slug": slug, "count": len(collected.contents)},
        )
        embeddings_result, vectors_empty = _compute_embeddings_for_markdown(
            collected,
            embeddings_client,
            logger,
            slug,
        )
        if embeddings_result is None:
            _log_index_skips(
                logger,
                slug,
                skipped_io=collected.skipped_io,
                skipped_empty=collected.skipped_empty,
                vectors_empty=vectors_empty,
            )
            try:
                m.set_artifacts(0)
            except Exception:
                m.set_artifacts(None)
            ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info(
                "semantic.index.done",
                extra={"slug": slug, "ms": ms, "artifacts": {"inserted": 0, "files": total_files}},
            )
            return 0

        logger.info(
            "semantic.index.embed.done",
            extra={"slug": slug, "count": len(embeddings_result.contents)},
        )

        _log_index_skips(
            logger,
            slug,
            skipped_io=collected.skipped_io,
            skipped_empty=collected.skipped_empty,
            vectors_empty=embeddings_result.vectors_empty,
        )

        logger.info(
            "semantic.index.persist.start",
            extra={"slug": slug, "files": len(embeddings_result.contents)},
        )
        inserted_total = _persist_markdown_embeddings(
            embeddings_result,
            scope=scope,
            slug=slug,
            db_path=db_path,
            logger=logger,
        )
        logger.info(
            "semantic.index.persist.done",
            extra={"slug": slug, "inserted": inserted_total, "files": len(embeddings_result.contents)},
        )

        ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "semantic.index.done",
            extra={
                "slug": slug,
                "ms": ms,
                "artifacts": {"inserted": inserted_total, "files": len(embeddings_result.contents)},
            },
        )
        try:
            m.set_artifacts(inserted_total)
        except Exception:
            m.set_artifacts(None)
        return inserted_total


def _build_inverse_index(vocab: Dict[str, Dict[str, Set[str]]]) -> Dict[str, Set[str]]:
    inv: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        for term in {canon, *(meta.get("aliases") or set())}:
            t = str(term).strip().lower()
            if t:
                inv.setdefault(t, set()).add(canon)
    return inv


def _parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    if not md_text.startswith("---"):
        return {}, md_text
    try:
        import yaml
    except Exception:
        return {}, md_text
    try:
        import re as _re

        m = _re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=_re.DOTALL)
        if not m:
            return {}, md_text
        header = m.group(1)
        body = md_text[m.end() :]
        meta = yaml.safe_load(header) or {}
        if not isinstance(meta, dict):
            return {}, md_text
        return cast(Dict[str, Any], meta), body
    except Exception:
        return {}, md_text


def _dump_frontmatter(meta: Dict[str, Any]) -> str:
    try:
        import yaml

        return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip() + "\n---\n"
    except Exception:
        lines = ["---"]
        if "title" in meta:
            title_val = str(meta["title"]).replace('"', '\\"')
            lines.append(f'title: "{title_val}"')
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        lines.append("---\n")
        return "\n".join(lines)


def _as_list_str(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, str):
        s = x.strip()
        return [s] if s else []
    if isinstance(x, (list, tuple, set)):
        out: list[str] = []
        for it in x:
            if it is None:
                continue
            s = str(it).strip()
            if s:
                out.append(s)
        return out
    s = str(x).strip()
    return [s] if s else []


def _merge_frontmatter(existing: Dict[str, Any], *, title: Optional[str], tags: List[str]) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        left = _as_list_str(meta.get("tags"))
        # Comportamento richiesto dai test: unione, deduplica e ORDINE ALFABETICO
        merged = sorted(set([*left, *tags]))
        meta["tags"] = merged
    return meta


@lru_cache(maxsize=1024)
def _term_to_pattern(term: str) -> re.Pattern[str]:
    r"""Pattern robusto a confini parola *semantici* (spazi = \s+)."""
    esc = re.escape(term.strip().lower())
    esc = esc.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){esc}(?!\w)")


def _guess_tags_for_name(
    name_like_path: str,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    inv: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    if not vocab:
        return []
    if inv is None:
        inv = _build_inverse_index(vocab)
    s = name_like_path.lower()
    s = re.sub(r"[_\/\-\s]+", " ", s)

    found: Set[str] = set()
    for term, canon_set in inv.items():
        if not term:
            continue
        pat = _term_to_pattern(term)
        if pat.search(s):
            found.update(canon_set)
    return sorted(found)


def _canonicalize_tags(raw_tags: List[str], inv: Dict[str, Set[str]]) -> List[str]:
    canon: Set[str] = set()
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if not normalized:
            continue
        mapped = inv.get(normalized)
        if mapped:
            canon.update(mapped)
        else:
            canon.add(tag.strip())
    return sorted(canon)
